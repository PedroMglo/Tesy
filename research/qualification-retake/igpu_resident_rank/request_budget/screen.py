"""Bound the traffic and time left for a decode-only intervention in both real packed turns."""

import argparse
import json
from decimal import ROUND_CEILING
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[1]
CLOCK = run_path(QUAL / "nvme_conversation/phase_reads/screen.py")
ns, sha, need, read = (CLOCK[k] for k in ("ns", "sha", "require", "read"))
ARMS = {
    "rop": (78, "r02", "1cef0f0e32e21f3304812479f5eb34e7f166423b85a96832210578c4dbf9aafb"),
    "por": (80, "r01", "1f1f819076b6ea26ba3a5a04b064cae662fd11f8a0f93ee94abb3f2efff286d4"),
}
TARGET = 10_000_000_000


def endpoint(journal, name):
    for i, item in enumerate(journal):
        line = item.get("fragment", "")
        if item["kind"] == "SSE_FRAGMENT" and line.startswith("data: {"):
            frame = json.loads(line[6:])
            if any((c["delta"].get(name) or "").strip() for c in frame["choices"]):
                return ns(item["monotonic_s"]), ns(journal[i + 1]["monotonic_s"], ROUND_CEILING)
    raise ValueError("missing SSE endpoint " + name)


def samples(rows, identity, origin):
    result = []
    for row in rows:
        need(row["pid"] == identity["pid"] and row["process_identity"] == identity, "process")
        center = origin + ns(row["elapsed_s"])
        vals = tuple(row["proc"][k] for k in CLOCK["KEYS"])
        need(all(type(x) is int and x >= 0 for x in vals), "counter type")
        point = CLOCK["Sample"](
            center - 500_001 - ns(row["collection_s"], ROUND_CEILING), center + 500_001, vals
        )
        if result:
            prior = result[-1]
            need(
                prior.hi < point.lo
                and all(a <= b for a, b in zip(prior.counters, vals, strict=True)),
                "sample overlap or counter regression",
            )
        result.append(point)
    return result


def boundary(first_final, span, steps, lower_bytes, bandwidth):
    need(steps > 0 and 0 < span <= first_final and bandwidth > 0, "phase geometry")
    available = TARGET - (first_final - span)
    max_bytes = max(0, available) * bandwidth // 10**9
    return dict(
        steps=steps,
        observed_span_ns=span,
        remaining_ns=available,
        required_removed_fraction=(first_final - TARGET) / span,
        max_average_ns_per_step=available / steps,
        max_link_bytes=max_bytes,
        critical_fraction_of_lower_bytes=max_bytes / lower_bytes if lower_bytes else None,
        seconds_if_all_lower_bytes_cross=lower_bytes / bandwidth if lower_bytes else None,
    )


def assess(archive, order, bandwidth):
    part, run, step_sha = ARMS[order]
    date = "20261125"
    directory = archive / f"part-{part}"
    manifest_file = directory / "manifest.json"
    receipt_dir = QUAL / "packed_nvme_manifest/server_profile/conversation/evidence"
    manifest_sha = read(receipt_dir / f"archive-{part}.json")["manifest"]["sha256"]
    need(sha(manifest_file) == manifest_sha, "private archive manifest")
    manifest = read(manifest_file)["files"]
    root = f"tesy-c281-{order}-natural-{date}-{run}/P/"
    stem = f"raw/tesy-c281-nvme-{order}-{date}-{run}-p"

    def verified(name):
        info = manifest[root + name]
        path = directory / (root + name)
        need(path.stat().st_size == info["bytes"] and sha(path) == info["sha256"], "raw " + name)
        return path

    step_path = QUAL / f"history_lookup/packed_step_budget/{order}.json"
    need(sha(step_path) == step_sha, "sample-45 assignment")
    step = read(step_path)
    arm_file = verified("arm.json")
    grade = read(arm_file)["grade"]
    need(
        sha(arm_file) == step["arm_sha256"]
        and grade["unit_closed"]
        and grade["transport"]["mode"] == "P",
        "packed arm",
    )
    raw = read(verified("raw/T2-result.json"))
    journal = CLOCK["lines"](verified("raw/T2-request.jsonl"))
    client = read(verified("client-receipt.json"))
    launch = read(verified(stem + ".launch.json"))
    mon = read(verified(stem + ".json"))
    identity = launch["process_identity"]
    need(client["process_identity"] == mon["process_identity"] == identity, "common PID")
    need(raw["accepted"] and journal[-1]["accepted"] and raw["timings"]["predicted_n"] == 47, "T2")
    start = ns(raw["request_started_monotonic"])
    reason = start + ns(raw["stream_metrics"]["first_reasoning_chunk_s"])
    finish = start + ns(raw["stream_metrics"]["first_final_content_chunk_s"])
    r0, r1 = endpoint(journal, "reasoning_content")
    f0, f1 = endpoint(journal, "content")
    need(r0 - 2 <= reason <= r1 + 2 and f0 - 2 <= finish <= f1 + 2, "SSE cut bracket")
    need(
        abs(finish - start - step["first_final_ns"]) <= 2 and r1 < f0, "sampled arm and client cut"
    )
    origin = launch["start_inventory"]["popen_invoked_monotonic_ns"]
    raw_receipt = read(verified("receipt.json"))
    closed = raw_receipt["transport"]["shutdown"]["server_port_scope_verified_ns"]
    upper = min(
        ns(client["ready_monotonic"], ROUND_CEILING) + CLOCK["MARGIN"],
        closed - ns(mon["elapsed_s"]) + 500_001,
    )
    shift = upper - origin
    sample_file = verified(stem + ".samples.jsonl")
    need(
        sha(sample_file) == grade["sample_sha256"] == mon["output_sha256"][".samples.jsonl"],
        "monitor seal",
    )
    rows = samples(CLOCK["lines"](sample_file), identity, origin)
    subwindow = CLOCK["between"](reason, finish)
    bounds = CLOCK["extrema"](rows, subwindow, shift)
    enough = bounds["definitely_inside_samples"][0] >= 2
    lower = bounds["counters"]["read_bytes"]["min"] if enough else 0
    budgets = {}
    for name, win in step["windows"].items():
        count = win["evaluations_through_cut"]
        need(count == 44 and win["first_final_sample_one_based"] == 45, "44 evaluated steps")
        budgets[name] = boundary(
            step["first_final_ns"], win["before_total_ns"], count, lower, bandwidth
        )
    return dict(
        arm_sha256=step["arm_sha256"],
        archive_manifest_sha256=manifest_sha,
        sample_sha256=grade["sample_sha256"],
        comparison_sha256=step_sha,
        first_final_ns=step["first_final_ns"],
        native_excess_ns_for_six_tok_s=int(step["decode_ns"]) - (47 * 10**9 // 6),
        subwindow_ns=finish - reason,
        max_common_clock_shift_ns=shift,
        accounting="CONTAINED_PROCESS_IO" if enough else "INCONCLUSIVE_SAMPLES",
        counter_bounds=bounds,
        budgets=budgets,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir()
    try:
        pci = Path("/sys/class/nvme/nvme0/device")
        speed = (pci / "max_link_speed").read_text().strip()
        width = (pci / "max_link_width").read_text().strip()
        need((speed, width) == ("16.0 GT/s PCIe", "4"), "laptop link inventory")
        bandwidth = 16_000_000_000 * int(width) // 8
        output = dict(
            status="CONDITIONAL_DECODE_ONLY_BUDGET",
            max_link_speed=speed,
            max_link_width=int(width),
            bandwidth_ceiling_B_s=bandwidth,
            protocol_sha256=sha(HERE / "protocol.md"),
            source_sha256=sha(Path(__file__)),
            arms={k: assess(args.archive, k, bandwidth) for k in ARMS},
        )
    except Exception as error:
        output = dict(status="FAIL_PRESERVED", reason=str(error))
    with (args.new_output_dir / "receipt.json").open("x") as out:
        print(json.dumps(output, indent=2, sort_keys=True), file=out)
    print(output["status"], output.get("reason", ""))
    raise SystemExit(int(output["status"] == "FAIL_PRESERVED"))
