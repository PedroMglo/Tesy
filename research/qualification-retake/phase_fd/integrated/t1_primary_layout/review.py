"""Recompute the paired four-cell result from closed, model-free service journals."""

import argparse
import hashlib
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORDER = ("ABCD", "ABDC", "BCAD", "CDBA", "DACB")
STRATA = ("148_cpu", "148_cuda", "decode_cpu", "decode_cuda")


def need(value, reason):
    if not value:
        raise ValueError(reason)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analyse(root):
    r = json.loads((root / "receipt.json").read_bytes())
    log = root / "raw/blocks.jsonl"
    mon = root / "raw/service-monitor.jsonl"
    inventory = root / "inventory.json"
    inv = json.loads(inventory.read_bytes())
    need(
        r["status"] == "PASS_RAM_TRANSPORT"
        and digest(log) == r["block_sha256"]
        and digest(mon) == r["monitor_sha256"]
        and digest(inventory) == r["inventory_sha256"],
        "physical hashes",
    )
    rows = [json.loads(line) for line in log.read_bytes().splitlines()]
    need(
        [(r["block"], r["cell"]) for r in rows]
        == [(n, c) for n, seq in enumerate(ORDER) for c in seq],
        "balanced block order",
    )
    medians = {k: [] for k in "ABCD"}
    bytes_by_cell = {}
    comparisons = []
    for b in range(5):
        times = {}
        for row in rows[4 * b : 4 * b + 4]:
            arm = row["cell"]
            waves = row["waves"]
            need(
                set(waves) == set(STRATA) and [waves[k]["served"] for k in STRATA] == [12, 9, 4, 4],
                "same routed work",
            )
            ts = sum(v["ns"] for v in waves.values())
            n = sum(v["read_bytes"] for v in waves.values())
            need(ts > 0 and n > 0 and bytes_by_cell.setdefault(arm, n) == n, "stable volume")
            times[arm] = ts
            if b:
                medians[arm].append(ts)
        if b:
            need(times == r["contrasts"]["blocks"][b - 1]["ns"], "clock sum")
            arms = (
                ("layout_after_policy", "C", "D"),
                ("policy_after_layout", "B", "D"),
                ("combined", "A", "D"),
                ("layout_only", "A", "B"),
                ("policy_only", "A", "C"),
            )
            comparisons.append({k: 100 * (times[a] - times[c]) / times[a] for k, a, c in arms})
    need(
        5 * sum(bytes_by_cell.values()) == r["arm_read_bytes"] and r["verified_components"] == 1740,
        "returned bytes and component checks",
    )
    samples = [json.loads(line) for line in mon.read_bytes().splitlines()]
    all_samples = [j["observation"] for j in samples] + [
        json.loads(line)["observation"]
        for line in (root / "raw" / (r["unit"] + ".start-inventory.jsonl"))
        .read_bytes()
        .splitlines()
    ]
    return dict(
        arm=r["arm"],
        median_ms={k: statistics.median(v) / 1e6 for k, v in medians.items()},
        paired_percent={k: statistics.median(a[k] for a in comparisons) for k in comparisons[0]},
        positive={k: sum(a[k] > 0 for a in comparisons) for k in comparisons[0]},
        contrast_blocks=r["contrasts"]["blocks"],
        read_bytes=bytes_by_cell,
        read_total=r["arm_read_bytes"],
        compute_gpu=0,
        forwards=0,
        peak_bytes=r["peak_bytes"],
        cpu_c=max(j["thermal"]["cpu_tctl_c"] for j in all_samples),
        nvme_c=max(max(j["thermal"]["nvme_composite_by_sensor"].values()) for j in all_samples),
        gpu_c=max(j["gpu"]["temperature_c"] for j in all_samples),
        gpu_used_mib=max(j["gpu"]["used_mib"] for j in all_samples),
        inventory_samples=inv["sample_count"],
        inventory_seconds=inv["duration_s"],
        prep_seconds=r["prepare_ns"] / 1e9,
        receipt_sha256=digest(root / "receipt.json"),
        partial_sha256=r["partial_sha256"],
        max_rss_limit_bytes=r["resource_cap"],
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("first", "second", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    arms = [analyse(a.first), analyse(a.second)]
    need(
        [r["arm"] for r in arms] == [1, 2]
        and arms[0]["partial_sha256"] == arms[1]["partial_sha256"]
        and arms[0]["read_bytes"] == arms[1]["read_bytes"],
        "paired process identity",
    )
    keys = ("layout_after_policy", "policy_after_layout", "combined")
    passes = [
        all(
            r["positive"][k] >= 3
            and r["paired_percent"][k] > 0
            and statistics.median(b[j] for b in r["contrast_blocks"]) > 0
            for k, j in zip(keys, ("layout_on_new", "policy_on_pack", "combined"), strict=True)
        )
        for r in arms
    ]
    physical = json.loads((a.second / "receipt.json").read_bytes())
    need(physical["both_processes_pass"] == all(passes), "native decision agreement")
    result = dict(
        status="GO_DESTINATION_FIXTURE_ONLY"
        if all(passes)
        else "INCONCLUSIVE"
        if any(passes)
        else "NO_GO_IN_THIS_FIXTURE",
        arms=arms,
    )
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(result["status"])


if __name__ == "__main__":
    main()
