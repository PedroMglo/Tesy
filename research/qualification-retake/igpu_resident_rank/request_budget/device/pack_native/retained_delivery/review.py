"""Reopen preserved failures, numerical controls, provider identities, T1 intent and T2 reads."""

import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
RUN = run_path(str(HERE / "run.py"))
sha, need = RUN["sha"], RUN["need"]
FAIL = "8e958fbf1dd894378abe9a4c7a052b56affc58993350ed5a1974bff44d046b2e"
PASS = "7fd60becc8295320dd833131501a84228aa2f8ec4ac985853f1d40965a82c74b"


def pinned(path, digest):
    need(sha(path) == digest, f"SHA256 {path.name}")
    return json.loads(path.read_bytes())


def verify(failed, passed, session):
    bad = pinned(failed / "receipt.json", FAIL)
    good = pinned(passed / "receipt.json", PASS)
    need(
        bad["status"] == "FAIL_PRESERVED"
        and not bad["cases"]
        and bad["commands"]["freq_disk"]["returncode"] == 1
        and good["status"] == "PASS_CAUSAL_RETAINED_CPU_DELIVERY",
        "terminal states",
    )
    for folder, data in ((failed, bad), (passed, good)):
        for stage, item in data["commands"].items():
            for name, ref in item["logs"].items():
                blob = folder / stage / name
                need(
                    sha(blob) == ref["sha256"] and blob.stat().st_size == ref["bytes"],
                    "command logs",
                )
        actual = pinned(folder / "replay/raw.json", data["replay"]["raw_sha256"])
        selection = pinned(session / "ON/before-t2-candidates.json", RUN["CAND"])
        need(
            actual
            == {
                **selection["banks"],
                "offered_keys": selection["offered_keys"],
                "prefix_records": 87736,
            },
            "native candidate and LRU against Python seal",
        )
    gold = pinned(passed / "gold.json", good["gold_sha256"])
    profiles = {}
    for mode in RUN["ARMS"]:
        entry = good["cases"][mode]
        row = pinned(passed / mode / "raw.json", entry["raw_sha256"])
        summary = RUN["verify"](mode, row, gold)
        need(
            summary | {"raw_sha256": entry["raw_sha256"]} == entry
            and row["providers"] == good["binary"]["load_paths"],
            "reopen per-job service and bindings",
        )
        profiles[mode] = summary
    mem = good["scope_after"]
    return {
        "status": "REPRODUCED_CAUSAL_RETAINED_CPU_DELIVERY",
        "failed_family_sha256": FAIL,
        "passed_family_sha256": PASS,
        "freeze": good["commit"],
        "backend_pin": good["backend_pin"],
        "binary_sha256": good["binary"]["sha256"],
        "pack_sha256": good["pack_sha256"],
        "pack_proof_bytes": good["pack_proof_bytes"],
        "modeled_products": 0,
        "resource": {
            "duration_s": good["elapsed_s"],
            "peak_bytes": mem["memory.peak"],
            "swap_bytes": mem["memory.swap.current"],
            "events": mem["memory.events"],
        },
        "capture": {
            "prefix_records": 87736,
            "offers": actual["prefill"]["offers"],
            "unique_offers": len(actual["offered_keys"]),
            "selection_sha256": RUN["CAND"],
            "lru": {k: v for k, v in actual["lru"].items() if k != "ordered_keys"},
            "prefill": {k: v for k, v in actual["prefill"].items() if k != "ordered_keys"},
        },
        "physical_arms": profiles,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("failed", "passed", "session", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = verify(a.failed, a.passed, a.session)
    except Exception as exc:
        result = {"status": "FAIL_PRESERVED", "reason": str(exc)}
    with (a.new_output_dir / "receipt.json").open("x") as out:
        json.dump(result, out, sort_keys=True, indent=2)
        out.write("\n")
    print(result["status"], result.get("reason", ""))
    raise SystemExit(int(result["status"] == "FAIL_PRESERVED"))
