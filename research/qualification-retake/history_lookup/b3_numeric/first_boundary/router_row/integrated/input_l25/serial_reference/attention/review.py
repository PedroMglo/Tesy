"""Reopen both same-driver captures, their same-mode controls and the cross-mode attention edge."""

import argparse
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
P = run_path(str(HERE / "pair.py"))
S, R, PF, need, read, sha, save = (P[k] for k in ("S", "R", "PF", "need", "read", "sha", "save"))


def audit_process(folder, unit, mode, arm, build):
    raw = folder / "raw"
    manifest, launch = (read(raw / (unit + ext)) for ext in (".json", ".launch.json"))
    cmd = read(folder / "attention-argv.json")
    cfg = read(folder / "attention-resource.json")
    pins = cfg["pinned"]
    env = {}
    start = cmd.index("--env")
    for i in range(start, cmd.index("--", start), 2):
        key, value = cmd[i + 1].split("=", 1)
        need(cmd[i] == "--env" and key not in env, "child env argument")
        env[key] = value
    need(
        env.get("TESY_B3_ROUTER_ROW") == "1"
        and env == manifest["explicit_env"]
        and manifest["relevant_environment"].get("TESY_B3_ROUTER_ROW") == "1"
        and manifest["process_identity"] == launch["process_identity"]
        and manifest["command"] == cmd[-6:]
        and cmd[-2] == mode
        and pins["capture_sha256"] == build["elf_sha256"]
        and cfg["scientific_protocol_sha256"] == P["B"]["METHOD"]
        and arm["maxima"] == manifest["maxima"]
        and arm["scope_cleanup"]
        and manifest["limits"]["resource_protocol_sha256"]
        == launch["resource_protocol_sha256"]
        == sha(folder / "attention-resource.json")
        and manifest["elapsed_s"] == arm["model_s"],
        "audited native scope",
    )
    core_env = {k: v for k, v in env.items() if k != "TESY_B3_ROUTER_ROW"}
    PF["check_native_manifest"](
        dict(manifest, explicit_env=core_env), cfg, pins, core_env, P["measure"]
    )
    compact = P["G"]["probes"].load(
        S["QUAL"] / "nvme_r0_gate/qualified_profile/compact.py", "attn_audit_inventory"
    )
    inventory = compact.validate_inventory(folder, unit, {"native_explicit_env": env}, launch)
    need(inventory == arm["c118"], "resource inventory")
    return dict(
        unit=unit,
        scope_s=arm["scope_s"],
        model_s=arm["model_s"],
        maxima=arm["maxima"],
        live_samples=arm["live_samples"],
        c118=inventory,
        gpu_energy=R["power"](folder, {"unit": unit}),
        cleanup=arm["scope_cleanup"],
        c55_age_s=arm["c55_age_s"],
    )


def audit(a):
    run = R["reopen"](a.family, a.receipt_sha256)
    ctrl = R["reopen"](a.reference, R["NUMERIC"])
    serial = R["reopen"](a.serial, P["SERIAL"])
    _, block = S["archive_controls"](a.archive)
    need(
        sha(a.build / "receipt.json") == P["BUILD"]
        and sha(a.window / "receipt.json") == run["window_sha256"]
        and run["status"] == "MEASURED_SAME_DRIVER_ATTENTION_CUT"
        and run["source_sha256"] == sha(HERE / "pair.py")
        and run["model_starts"] == 2
        and run["generation_requests"] == 0
        and run["protocol_sha256"] == sha(HERE / "protocol.md")
        and run["build_sha256"] == P["BUILD"],
        "sealed family",
    )
    build = read(a.build / "receipt.json")
    win = read(a.window / "receipt.json")
    need(
        win["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and sha(a.window / "samples.jsonl") == win["window_sha256"]
        and sha(a.build / "b3-numeric") == build["elf_sha256"]
        and sha(a.build / "libllama.so.0.0.9884") == build["graph_sha256"] == P["B"]["IMAGE"],
        "build and admission",
    )
    pins = read(S["QUAL"] / "nvme_r0_gate/inputs/receipt.json")
    gold = a.reference / "raw" / (ctrl["unit"] + ".capture")
    need(P["prepare"].tree_digest(gold) == pins["gold"], "current R0")
    caps, arms = {}, {}
    for mode, baseline in (("AR", a.serial / "raw" / (serial["unit"] + ".capture")), ("B3", block)):
        unit = run["unit"] + "-" + mode.lower()
        directory = a.family / mode
        caps[mode] = directory / "raw" / (unit + ".capture")
        arm = run["arms"][mode]
        runtime = audit_process(directory, unit, mode, arm, build)
        observation = P["grade_arm"](caps[mode], mode, gold, baseline, pins)
        need(
            observation == read(directory / "same-mode.json")
            and sha(directory / "same-mode.json") == arm["same_mode_sha256"],
            "same mode",
        )
        arms[mode] = dict(runtime=runtime, observation=observation)
    ar, block = (arms[m]["observation"]["states"] for m in ("AR", "B3"))
    need(
        all(ar[k] == block[k] for k in ("initial-kv.bin", "initial-pool.bin")),
        "AR and B3 initial state",
    )
    compared = P["grade_pair"](caps["AR"], caps["B3"])
    need(
        compared == read(a.family / "pair.json")
        and sha(a.family / "pair.json") == run["pair_sha256"],
        "independent pair",
    )
    return dict(
        status="REPRODUCED_SAME_DRIVER_ATTENTION_CUT",
        family_sha256=a.receipt_sha256,
        commit=run["commit"],
        tree=run["tree"],
        protocol_sha256=run["protocol_sha256"],
        build_sha256=P["BUILD"],
        elf_sha256=build["elf_sha256"],
        graph_sha256=build["graph_sha256"],
        window_sha256=run["window_sha256"],
        driver=win["gpu_driver"],
        gpu=win["gpu_name"],
        model_sha256=serial["model_sha256"],
        current_r0_sha256=R["NUMERIC"],
        serial_sha256=P["SERIAL"],
        historical_block_sha256=S["FAMILY"],
        arms=arms,
        comparison=compared["positions"],
        model_starts=2,
        generation_requests=0,
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("family", "reference", "serial", "archive", "build", "window", "new-output-dir"):
        cli.add_argument("--" + name, type=Path, required=True)
    cli.add_argument("--receipt-sha256", required=True)
    args = cli.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    result = audit(args)
    save(args.new_output_dir / "result.json", result)
    print(result["status"])
