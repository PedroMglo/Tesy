"""Read one closed private C281 session and publish only counts, timings and digests."""

import argparse
import json
from pathlib import Path

from contract import C281, CAP, check, ids_hash, load, sha256


def summarize(root):
    raw = root / "raw"
    receipt = load(root / "receipt.json")
    preset = load(root / "preset.json")
    run = preset["run_id"]
    monitor = load(raw / (run + ".json"))
    aggregate = load(root / "client-receipt.json")
    check(
        receipt["status"] == "PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY"
        and receipt["model_launches"] == 1
        and sha256(root / "preset.json") == receipt["preset_sha256"]
        and sha256(raw / (run + ".json")) == receipt["monitor_sha256"],
        "not the closed successful session",
    )
    check(
        aggregate["status"] == "CLIENT_TWO_REQUESTS_PASS"
        and monitor["returncode"] == 0
        and monitor["stop_reason"] == "INTERRUPTED_BY_OWNER",
        "lifecycle",
    )
    check(
        monitor["cgroup_start"]["memory_high"] == monitor["cgroup_start"]["memory_max"] == CAP,
        "historical E20",
    )
    rows = []
    for i, (summary, original) in enumerate(
        zip(receipt["rows"], load(C281 / "compact.json")["rows"], strict=True), 1
    ):
        prefix = raw / f"T{i}"
        inp = load(Path(str(prefix) + "-input.json"))
        full = load(Path(str(prefix) + "-result.json"))
        check(full["accepted"] is True, "response not accepted")
        check(full["content_gate"] == full["prefix_gate"] == "PASS", "validator")
        check(
            ids_hash(inp["official_ids"])
            == summary["official_ids_sha256"]
            == original["official_ids_i32le_sha256"]
            and sha256(Path(str(prefix) + "-input.json")) == original["input_raw_sha256"],
            "input equivalence",
        )
        s = [
            json.loads(line)
            for line in Path(str(prefix) + "-request.jsonl").read_text().splitlines()
        ]
        check(
            s[0]["kind"] == "REQUEST_START"
            and s[-1]["kind"] == "REQUEST_TERMINAL"
            and s[-1]["accepted"]
            and full["stream_metrics"]["done_observed"],
            "stream/terminal",
        )
        row = summary.copy()
        transport = row.pop("valid_wall_s")
        row.update(
            transport_complete_s=transport,
            validated_terminal_s=s[-1]["monotonic_s"] - full["request_started_monotonic"],
            first_text_s=full["stream_metrics"]["first_text_chunk_s"],
            tpot_s=summary["decode_s"] / summary["predicted_n"],
            output_ids_authority=full["output_ids_authority"],
        )
        check(
            row["validated_terminal_s"]
            >= transport
            >= row["first_final_s"]
            >= row["first_text_s"]
            > 0,
            "client clock chronology",
        )
        rows.append(row)
    two = rows[1]
    budget = two["predicted_n"] / 6
    files = {
        str(p.relative_to(root)): {"bytes": p.stat().st_size, "sha256": sha256(p)}
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }
    return dict(
        status=receipt["status"],
        measurement_commit=preset["measurement_commit"],
        tree=preset["tree"],
        protocol_sha256=preset["protocol_sha256"],
        unit=run,
        c270_receipt_sha256=preset["c270_receipt_sha256"],
        window_receipt_sha256=preset["window_sha256"],
        r0_cgroup_cap_bytes=CAP,
        server_started_utc=monitor["started_utc"],
        server_ended_utc=monitor["ended_utc"],
        server_elapsed_s=monitor["elapsed_s"],
        ready_after_popen_s=receipt["ready_s"],
        complete_envelope_s=receipt["envelope_s"],
        session_date=preset["session_date"],
        rows=rows,
        requests=2,
        valid_requests=2,
        model_launches=1,
        first_final_le_10s=receipt["nominal_first_final_le_10s"],
        decode_ge_6=receipt["nominal_decode_ge_6"],
        conditional_residual_first_final_minus_all_decode_s=two["first_final_s"] - two["decode_s"],
        decode_budget_for_count_at_6_s=budget,
        conditional_decode_saving_needed_s=two["decode_s"] - budget,
        cgroup_events_local=monitor["cgroup_end"]["events_local"],
        cleanup=receipt["cleanup"],
        maxima=receipt["maxima"],
        forwards="NOT_INSTRUMENTED",
        physical_energy_j=None,
        volume_bytes=sum(v["bytes"] for v in files.values()),
        local_manifest=files,
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-root", required=True, type=Path)
    ap.add_argument("--new-output-dir", required=True, type=Path)
    a = ap.parse_args()
    summary = summarize(a.raw_root)
    a.new_output_dir.mkdir()
    with (a.new_output_dir / "evidence.json").open("x") as stream:
        json.dump(summary, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
