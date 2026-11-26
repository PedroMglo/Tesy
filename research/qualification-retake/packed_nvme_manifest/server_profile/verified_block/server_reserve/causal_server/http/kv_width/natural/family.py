"""Execute independent serial controls and the repaired block at the same natural T1 boundary."""

import argparse
import hashlib
import os
import re
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
C = run_path(str(HERE / "client.py"))
F, G, need, sha, save = (C[k] for k in ("F", "G", "need", "sha", "save"))
S = F["S"]
CLIENT = "30fe606906a7b8862c7ba09d1832fdec0a04c50b3567a933abb38079176cc148"
CASES = {"P": ("HIST1", "HIST", 1), "OFF": ("OFF1", "WIDE", 1), "ON": ("ON3", "WIDE", 3)}
read = F["read"]


def grade(cap, reference, work, mode):
    n = 2065
    native = read(cap / "native.json")
    need(
        native["mode"] == mode
        and native["reserve"] == CASES[mode][2]
        and native["positions"] == 2062
        and native["prefix"] == work["prefix"]
        and native["verified"] == work["expected"],
        "target decisions",
    )
    parts = sorted(cap.glob("end-*.kv"))
    need(
        1 <= len(parts) <= 6
        and [p.name for p in parts] == [f"end-{i}.kv" for i in range(len(parts))]
        and all(p.stat().st_size == 16 << 20 for p in parts[:-1]),
        "complete KV shards",
    )
    blob = b"".join(p.read_bytes() for p in parts)
    record = native["end"]
    need(
        len(blob) == record["bytes"] and hashlib.sha256(blob).hexdigest() == record["sha256"],
        "whole KV",
    )
    kv = S["RB"]["SWA"]["KV"]
    banks = kv["layers_from_log"](cap.with_suffix(".stderr").read_bytes())
    offsets, _ = kv["parse"](blob, n, banks)
    new_counts = {
        bank: sum(1 for b, kind, layer, pos in offsets if b == bank and pos >= 2062)
        for bank in ("base", "swa")
    }
    need(new_counts == {"base": 108, "swa": 108}, "all three new positions across 36 layers")
    rows = [cap / k for k in ("prefill.f32", "entry.f32", "step-0.f32", "step-1.f32", "step-2.f32")]
    need(all(row.stat().st_size == 201088 * 4 for row in rows), "complete distributions")
    comparison = {}
    if mode != "P":
        ref = read(reference / "native.json")
        for key in ("entry", "end", "prefix", "verified", "store_entry"):
            comparison[key] = native[key] == ref[key]
        for row in [*rows, cap / "entry.pool", *parts]:
            comparison[row.name] = row.read_bytes() == (reference / row.name).read_bytes()
        if mode == "OFF":
            comparison["end.pool"] = (cap / "end.pool").read_bytes() == (
                reference / "end.pool"
            ).read_bytes()
            comparison["store_end"] = native["store_end"] == ref["store_end"]
    return dict(
        passed=all(comparison.values()),
        comparison=comparison,
        rows={r.name: sha(r) for r in rows},
        new_kv_rows=new_counts,
        kv_bytes=len(blob),
        entry=native["entry"],
        end=record,
        confirmed=len(native["verified"]),
        store_entry=native["store_entry"],
        store_end=native["store_end"],
    )


def arm(
    a,
    root,
    mode,
    build,
    prior,
    policy,
    model_id,
    *,
    study=None,
    extra_flags=None,
    check=None,
    reference=None,
    loader_cache=None,
):
    root.mkdir()
    case, library, reserve = CASES[mode]
    unit = a.unit + "-" + root.name.lower()
    ctl = S["Authority"](a, root, build, library)
    ctl.loader_cache = loader_cache
    src = case + "/packed-resource.json"
    old = G["read"](a.previous / src, prior["raw_sha256"][src])
    key = case + "/argv-packed.json"
    template = G["read"](a.previous / key, prior["raw_sha256"][key])["command"]
    raw = root / "raw"
    raw.mkdir()
    cfg = root / "natural-resource.json"
    cap = raw / (unit + ".capture")
    work = a.client / "work.json"
    so = build["arms"][library]["image_sha256"]
    sealed = old["pinned"] | dict(
        capture_sha256=build["elf_sha256"],
        ids_sha256=sha(work),
        numerical_dso_sha256=old["pinned"]["numerical_dso_sha256"] | {G["IMAGE"]: so},
        startup_dso_sha256={
            Path(v["file"]).name: v["sha256"]
            for k, v in ctl.verified["closure"].items()
            if k != G["START"]["LOADER"].name
        },
    )
    need(
        model_id == old["model_stat"] and sha(work) == build["work_sha256"],
        "current model and work",
    )
    shutil.copyfile(a.window / "resource-policy.json", root / "resource-policy.json")
    pro = old | dict(
        schema="tesy-natural-t1-cut-v1",
        execution_scope_unit=unit,
        case=mode,
        mode=mode,
        pinned=sealed,
        measurement_commit=a.commit,
        output_reserve=reserve,
        scientific_protocol_sha256=study or C["METHOD"],
        model_stat=model_id,
        resources=F["SESSION"].freeze_protocol_resource_limits(
            policy, cgroup_memory_max_bytes=20 << 30
        ),
        start_inventory=old["start_inventory"]
        | {"policy_sha256": sha(root / "resource-policy.json")},
    )
    F["SESSION"].validate_resource_protocol(pro)
    save(cfg, pro)
    cmd = template[: template.index("--env")]
    need(cmd.count("--unit=" + prior["unit"] + "-" + case.lower()) == 1, "old scope")
    cmd[cmd.index("--unit=" + prior["unit"] + "-" + case.lower())] = "--unit=" + unit
    k = cmd.index("--")
    cmd[k:k] = ["-p", "LimitCORE=0", "-p", "CoredumpFilter=0x0"]
    for arg, value in (
        ("--run-id", unit),
        ("--output-root", str(raw)),
        ("--variant", "C291-natural-cut-" + mode),
        ("--workload", str(work)),
        ("--resource-protocol", str(cfg)),
    ):
        cmd[cmd.index(arg) + 1] = value
    loader = dict(LD_LIBRARY_PATH=ctl.search, LD_DEBUG="libs", LD_DEBUG_OUTPUT=str(raw / "loader"))
    extra = {
        S["PK"]["live"].STORE_ENV: str(ctl.data_paths["manifest"]),
        "TESY_TEST_OUTPUT_RESERVE": str(reserve),
    }
    if mode == "ON":
        extra.update(S["RB"]["T"]["flags"]("CUDA"))
    if extra_flags:
        need(mode == "ON" and not extra.keys() & extra_flags.keys(), "new block-only switches")
        extra.update(extra_flags)
    expected = {"TESY_CPU_WAVE_SKIP_PARKED": "1"} | loader | extra
    for k, v in expected.items():
        cmd += ["--env", k + "=" + v]
    model = template[-5]
    need(Path(model).resolve(strict=True) == ctl.data_paths["model"], "model on internal NVMe")
    cmd += ["--", str(ctl.exe), model, str(work), mode, str(cap)]
    save(root / "invocation.json", dict(command=cmd, expected=expected))
    S["PK"]["PK"]["age"](policy, datetime.now(UTC))
    driver = S["N"]["AU"]["Authority"].monitor_proof(ctl.monitor)
    ident, samples, mapped, wall = S["PF"]["guarded_run"](
        cmd, root, unit, ctl, S["measure"], S["N"]["run_bounded"]
    )
    m, launch = (read(raw / (unit + s)) for s in (".json", ".launch.json"))
    need(
        m["explicit_env"] == expected
        and m["command"] == cmd[-5:]
        and m["process_identity"] == ident
        and launch["process_identity"] == ident
        and m["limits"]["resource_protocol_sha256"]
        == launch["resource_protocol_sha256"]
        == sha(cfg)
        and wall <= 320,
        "physical call",
    )
    standard = {k: v for k, v in expected.items() if k not in extra}
    S["PF"]["check_native_manifest"](
        dict(m, explicit_env=standard), pro, sealed, standard, S["measure"]
    )
    inventory = S["PK"]["PK"]["compact"].validate_inventory(
        root, unit, dict(native_explicit_env=expected), launch
    )
    age = S["PK"]["PK"]["age"](
        policy, datetime.fromisoformat(launch["start_inventory"]["popen_invoked_utc"])
    )
    fds = S["PK"]["live"].CaptureAuthority.fd_evidence(ctl)
    loaded = ctl.audit(raw, ident["pid"])
    need({Path(v).name for v in mapped} <= loaded["initialized"].keys(), "verified providers")
    log = cap.with_suffix(".stderr").read_text()
    need(
        re.findall(r"llama_context: n_outputs_max\s*=\s*(\d+)", log) == [str(reserve)],
        "live reserve",
    )
    widths = [int(k) for k in re.findall(r"^tesy_b3_built attention 25 (\d+)$", log, re.M)]
    need(
        (bool(widths) and set(widths) == {2304}) if mode == "ON" else not widths,
        "observed L25 KV width at dispatch",
    )
    ref = reference or root.parent / "P/raw" / (a.unit + "-p.capture")
    result = grade(cap, ref, read(work), mode)
    save(root / "grade.json", result)
    if check is None:
        need(
            result["passed"],
            "full-state or logits mismatch: "
            + str([k for k, v in result["comparison"].items() if not v]),
        )
    else:
        check(cap, result)
    return dict(
        status="PASS_NATURAL_T1_" + mode,
        grade_sha256=sha(root / "grade.json"),
        image_sha256=so,
        unit=unit,
        inventory=inventory,
        c55_age_s=age,
        gpu_driver=driver,
        fd=fds,
        loader=loaded,
        samples=samples,
        wall_s=wall,
        model_s=m["elapsed_s"],
        maxima=m["maxima"],
        observed_L25_widths=widths,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "previous",
        "static",
        "client",
        "window",
        "placement",
        "derived",
        "constructor",
        "new-output-dir",
    ):
        p.add_argument("--" + k, type=Path, required=True)
    for k in ("commit", "unit", "window-sha256"):
        p.add_argument("--" + k, required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    t = time.monotonic()
    r = dict(
        status="FAIL_PRESERVED", commit=a.commit, protocol_sha256=C["METHOD"], unit=a.unit, arms={}
    )
    try:
        h, r["tree"] = G["tree"](G["REPO"])
        need(
            h == a.commit
            and sha(HERE / "protocol.md") == C["METHOD"]
            and re.fullmatch("tesy-natural-cut-[a-z0-9-]+", a.unit),
            "source and scope",
        )
        win = G["read"](a.window / "receipt.json", a.window_sha256)
        need(
            win["status"] == "PASS_RESOURCE_WINDOW_ONLY"
            and sha(a.window / "samples.jsonl") == win["window_sha256"],
            "fresh C55",
        )
        policy, model_id = F["POST"].contract.placement(a.window, a.placement)
        build = G["read"](a.client / "receipt.json", CLIENT)
        prior = G["read"](a.previous / "receipt.json", F["F"]["GATE"])
        need(
            build["status"] == "GO_NATURAL_CLIENT_ONLY"
            and all(sha(Path(k)) == v for k, v in build["headers"].items()),
            "qualified natural client",
        )
        r.update(
            client_sha256=CLIENT,
            window_sha256=a.window_sha256,
            comparison="bitwise at first natural draft",
        )
        for mode in CASES:
            r["stage"] = mode
            r["arms"][mode] = arm(a, out / mode, mode, build, prior, policy, model_id)
        r["status"] = "GO_NATURAL_T1_DISTRIBUTIONS_AND_KV"
    except Exception as e:
        r.update(status="FAIL_PRESERVED", error=f"{type(e).__name__}: {e}")
    r.update(
        wall_s=time.monotonic() - t,
        model_starts=len(list(out.rglob("*.launch.json"))),
        generation_requests=0,
        files={str(k.relative_to(out)): sha(k) for k in sorted(out.rglob("*")) if k.is_file()},
    )
    save(out / "receipt.json", r)
    print(r["status"], r.get("error", ""), flush=True)
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
