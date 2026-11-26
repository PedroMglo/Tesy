"""Independently recompare the archived serial and three-position observations."""

import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
S = run_path(str(HERE / "probe.py"))
R, need, read, sha = (S[k] for k in ("R", "need", "read", "sha"))
STAGES = (
    ("attn_post_norm-24",),
    ("ffn_moe_out-24",),
    ("l_out-24",),
    ("attn_norm-25",),
    ("Qcur-25", "Kcur-25", "Vcur-25"),
    ("attn_out-25",),
    ("ffn_inp-25",),
    ("attn_post_norm-25",),
    ("ffn_moe_out-25",),
)


def summarize(pairs):
    rows = {}
    for pos in (189, 190, 191):
        first = []
        counts = {}
        for group in STAGES:
            differing = []
            for name in group:
                r = pairs[f"{pos}.{name}.bin"]
                need(
                    r["position"] == pos
                    and r["tensor"] == name
                    and 0 <= r["changed_words"] <= r["words"],
                    "misidentified row",
                )
                n = r["changed_words"]
                counts[name] = n
                if n:
                    differing.append(name)
            if differing and not first:
                first = differing
        rows[str(pos)] = dict(earliest_observed_differences=first, changed_F32=counts)
    need(len(pairs) == sum(len(g) for g in STAGES) * len(rows), "row coverage")
    return rows


def review(a):
    run = R["reopen"](a.family, a.receipt_sha256)
    ref = R["reopen"](a.reference, R["NUMERIC"])
    need(
        run["source_sha256"] == sha(HERE / "probe.py")
        and run["protocol_sha256"] == S["PROTOCOL"]
        and run["model_starts"] == 1
        and run["generation_requests"] == 0
        and run["status"] == "MEASURED_SERIAL_L25_WITNESS",
        "numerical family",
    )
    ar, b3 = S["archive_controls"](a.archive)
    gold = a.reference / "raw" / (ref["unit"] + ".capture")
    sealed = read(S["QUAL"] / "nvme_r0_gate/inputs/receipt.json")
    need(S["prepare"].tree_digest(gold) == sealed["gold"], "C127 independent whole tree")
    tagged = a.family / "raw" / (run["unit"] + ".capture")
    checked = S["compare"](
        tagged, gold, ar, b3, sealed, a.archive / "part-23/tesy-c270-driver-20261125-r01"
    )
    need(
        checked == read(a.family / "numeric.json")
        and sha(a.family / "numeric.json") == run["numerical_sha256"],
        "reproduced pairs",
    )
    unit = run["unit"]
    manifest = read(a.family / "raw" / (unit + ".json"))
    launch = read(a.family / "raw" / (unit + ".launch.json"))
    cfg = read(a.family / "serial-resource.json")
    command = read(a.family / "serial-argv.json")
    end = command.index("--", command.index("--env"))
    env = {}
    for i in range(command.index("--env"), end, 2):
        need(command[i] == "--env", "explicit environment")
        k, v = command[i + 1].split("=", 1)
        need(k not in env, "duplicate environment")
        env[k] = v
    need(
        "TESY_B3_ROUTER_ROW" not in env
        and manifest["process_identity"] == launch["process_identity"]
        and manifest["command"] == command[-6:]
        and command[-2] == "AR"
        and run["scope_cleanup"]
        and run["maxima"] == manifest["maxima"],
        "serial process",
    )
    S["PF"]["check_native_manifest"](manifest, cfg, cfg["pinned"], env, S["measure"])
    return dict(
        status="REPRODUCED_SERIAL_LAYER_25",
        private_family_sha256=a.receipt_sha256,
        commit=run["commit"],
        tree=run["tree"],
        protocol_sha256=S["PROTOCOL"],
        observer_sha256=S["ELF"],
        numerical_sha256=run["numerical_sha256"],
        reference_sha256=R["NUMERIC"],
        historical_block_sha256=S["FAMILY"],
        current_model_sha256=run["model_sha256"],
        driver=run["kernel"],
        positions=summarize(checked["pair_sha256_and_differences"]),
        numeric=checked,
        maxima=run["maxima"],
        scoped_s=run["scope_s"],
        model_s=run["model_s"],
        inventory=run["c118"],
        live_samples=run["live_samples"],
        gpu_energy=R["power"](a.family, run),
        model_starts=1,
        generation_requests=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for label in ("archive", "reference", "family", "new-output-dir"):
        p.add_argument("--" + label, required=True, type=Path)
    p.add_argument("--receipt-sha256", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    result = review(a)
    with (a.new_output_dir / "result.json").open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(result["status"])
