"""Verify the archived C269 capture against C127, then report phases and covered GPU energy."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
S = run_path(str(HERE / "screen.py"))
Q, REPO, need, sha = (S[k] for k in ("QUAL", "REPO", "need", "sha"))
ENERGY = run_path(str(Q / "phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/pair.py"))[
    "energy"
]
STATIC = "0c50a2657aa1dd5ba53a862e0e3e5cf4c2e366eb4663109ce2f2c03c2557df3b"
NUMERIC = "01303f006ce46c25b06238a4f953f3c2405ab96fae93c370d500f28b39d06741"
PILOT = "8fc33c06313d1a5888fb1bbb75c9c95cef361382fc6bfd127b0781b4962d602b"


def read(p):
    return json.loads(p.read_bytes())


def reopen(folder, digest):
    receipt = folder / "receipt.json"
    need(sha(receipt) == digest, "family receipt")
    r = read(receipt)
    files = {
        str(p.relative_to(folder)): sha(p)
        for p in folder.rglob("*")
        if p.is_file() and p != receipt
    }
    need(files == r["raw_sha256"], "raw file set")
    return r


def power(folder, r):
    raw, unit = folder / "raw", r["unit"]
    monitor = read(raw / (unit + ".json"))
    samples = [
        json.loads(line) for line in (raw / (unit + ".samples.jsonl")).read_bytes().splitlines()
    ]
    need(
        all(s["process_identity"] == monitor["process_identity"] for s in samples),
        "monitored process changed",
    )
    return ENERGY(samples, monitor["elapsed_s"])


def review(a):
    r = reopen(a.numeric, NUMERIC)
    pilot = reopen(a.pilot, PILOT)
    sf = a.static / "receipt.json"
    need(sha(sf) == STATIC, "static receipt")
    s = read(sf)
    for name, digest in s["raw_sha256"].items():
        need(sha(a.static / name) == digest, "static ELF query")
    need(
        set(s["arms"]) == {"C270_R0", "C270_PACK", "C281_R0", "C281_PACK"}
        and all(v["wrong_provider_rejected"] for v in s["arms"].values()),
        "static controls",
    )
    need(
        r["status"] == "GO_C269_CURRENT_C127"
        and r["static_sha256"] == STATIC
        and r["kernel"] == s["kernel"]
        and r["model_starts"] == 1,
        "numerical authority",
    )
    unit, raw = r["unit"], a.numeric / "raw"
    mon = read(raw / (unit + ".json"))
    need(
        mon["returncode"] == mon["maxima"]["swap_bytes"] == 0
        and mon["stop_reason"] is None
        and mon["mapped_libraries_match_ldd"]
        and mon["maxima"] == r["maxima"],
        "monitor or swap",
    )
    old = S["OLD"]["locks"](REPO)
    ref = Path(old[S["OLD"]["C270"]]["runs"][0]["post_run_command"][-1])
    sealed = old[S["OLD"]["Q"] + "nvme_r0_gate/inputs/receipt.json"]
    gate = REPO / "tools/block_layer_reuse_gate.py"
    need(
        sha(gate) == "2b47079f3eab3975e78da12f9fc9a0c40d0ced417375d91ab4e42d81e8e39017",
        "independent gate changed",
    )
    sys.path.insert(0, str(REPO / "tools"))
    from c94_session_wave_8k_reference import tree_digest

    need(tree_digest(ref) == sealed["gold"], "independent gold changed")
    capture = raw / (unit + ".capture")
    checked = a.new_output_dir / "selected.json"
    subprocess.run(
        [sys.executable, "-B", gate, capture, "--bridge-reference", ref, "--output", checked],
        capture_output=True,
        check=True,
        timeout=45,
    )
    need(
        sha(checked) == sha(a.numeric / "selected.json") == r["selected_sha256"],
        "independent numeric verdict",
    )
    grade = read(checked)
    inv = read(raw / (unit + ".start-inventory.receipt.json"))
    return dict(
        decision=r["status"],
        static_sha256=STATIC,
        numeric_sha256=NUMERIC,
        pilot_sha256=PILOT,
        commit=r["commit"],
        tree=r["tree"],
        kernel=r["kernel"],
        window_sha256=r["window_sha256"],
        model_sha256=r["model_sha256"],
        initialized_providers=r["loader"]["initialized"],
        static_closures={k: len(v["closure"]) for k, v in s["arms"].items()},
        unique_elf_B=s["unique_elf_B"],
        live_map_samples=r["samples_live"],
        raw_inventory_samples=inv["sample_count"],
        model_starts=1,
        generation_requests=0,
        numeric=grade,
        complete_tree_equals_C127=tree_digest(capture) == sealed["gold"],
        resource_maxima=mon["maxima"],
        elapsed_model_s=mon["elapsed_s"],
        wall_with_C118_s=r["wall_scoped_s"],
        numerical_power=power(a.numeric, r),
        natural_pilot_power=power(a.pilot, pilot),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("static", "numeric", "pilot", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    report = review(a)
    with (a.new_output_dir / "result.json").open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(report["decision"])
