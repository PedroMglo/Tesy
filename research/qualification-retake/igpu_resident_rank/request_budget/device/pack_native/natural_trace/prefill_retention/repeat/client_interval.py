"""Locate the diagnostic selector inside each measured T2 client clock."""

import argparse
import json
from decimal import Decimal
from pathlib import Path
from runpy import run_path

Q = run_path(str(Path(__file__).resolve().parents[1] / "evaluate.py"))
check, pinned = Q["check"], Q["pinned"]


def inspect(root, family_sha, repeat_file, repeat_sha):
    family = pinned(root / "family.json", family_sha)
    repeat = pinned(repeat_file, repeat_sha)
    check(repeat["inputs"]["family_sha256"] == family_sha, "same physical session")
    result = {}
    for mode in ("OFF", "ON"):
        arm = root / mode
        a = pinned(arm / "arm.json", family["arms"][mode]["sha256"])
        receipt = pinned(arm / "receipt.json", a["receipt_sha256"])
        proof = receipt["full_prefix"]
        payload = json.loads((arm / "raw/T2-result.json").read_bytes())
        start = int(Decimal(str(payload["request_started_monotonic"])) * 10**9)
        entry = proof["post_entry_ns"][1]
        first = receipt["rows"][1]["first_final_s"]
        check(
            first == payload["stream_metrics"]["first_final_content_chunk_s"]
            and start <= entry
            and 47 == receipt["rows"][1]["predicted_n"],
            "client scope",
        )
        bridge = {"client_start_to_stream_entry_ns": entry - start, "measured_first_final_s": first}
        if mode == "ON":
            pre = pinned(arm / "before-t2.json", proof["before_t2_sha256"])
            check(
                start
                <= pre["seal_start_ns"]
                <= pre["selection_saved_ns"]
                <= proof["seal_end_ns"]
                <= entry,
                "selector outside named interval",
            )
            budget = repeat["new"]["CPU_first_final_budget_ns"]
            bridge.update(
                selection_ns=proof["seal_end_ns"] - pre["seal_start_ns"],
                CPU_first_final_budget_ns=budget,
                budget_if_all_time_to_stream_entry_were_free_ns=budget + entry - start,
            )
        result[mode] = bridge
    return {
        "status": "DIAGNOSTIC_CLIENT_CLOCK_DECOMPOSITION",
        "family_sha256": family_sha,
        "repeat_sha256": repeat_sha,
        "arms": result,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("session", "repeat", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    for k in ("session-sha256", "repeat-sha256"):
        p.add_argument("--" + k, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        out = inspect(a.session, a.session_sha256, a.repeat, a.repeat_sha256)
    except Exception as exc:
        (a.new_output_dir / "FAIL.json").write_text(json.dumps({"error": str(exc)}) + "\n")
        raise
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(out, f, indent=2, sort_keys=True)
        f.write("\n")
