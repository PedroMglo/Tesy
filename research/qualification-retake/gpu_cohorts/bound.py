"""Conditional upper bounds for statically promoted, complete CPU-layer top-4s."""

import argparse
import hashlib
import itertools
import json
import resource
import signal
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import cache_boundary as c294  # noqa: E402
from warm_route_reference.verify import PROMPT, check_witness  # noqa: E402

MIB = 1 << 20
WEIGHT_BYTES = 13_219_200
US = 1_000_000
PROTOCOL = "85ab0a622e7892ab5405a9cf666500e1f8995448e2d537d17c87bdafc9d3d505"
FAMILY_SHA = "8cd41f2de3d183c121b8123bb1fd619c1803c5df6dd48d5676c1dde2158c857c"
R5_SHA = "9aededa28eb6ad62f2e186c7bd2cdd32bb974b47bd76d5c26cb08849f98062cf"


def verified(path, digest, size=None):
    if size is not None:
        c294.require(path.stat().st_size == size, "source length")
    data = path.read_bytes()
    c294.require(hashlib.sha256(data).hexdigest() == digest, "source digest")
    return data


def capacity(raw):
    family = json.loads(verified(HERE.parent / "warm_route_family/evidence-r1.json", FAMILY_SHA))
    window = HERE.parent / "nvme_admission/evidence-20261125-r5/window.json"
    lock = json.loads(verified(window, R5_SHA))["r5_manifest"]["resource-policy.json"]
    policy = json.loads(verified(raw / "resource-policy.json", lock["sha256"], lock["bytes"]))
    arms = {}
    for a in family["arms"]:
        name = a["run_id"]
        m = json.loads(verified(raw / "raw" / (name + ".json"), a["monitor_sha256"]))
        hi = m["cgroup_start"]["memory_high"]
        c294.require(
            m["stop_reason"] is None
            and m["returncode"] == 0
            and hi == m["cgroup_start"]["memory_max"] == 20 << 30
            and m["elapsed_s"] == a["model_wall_s"]
            and a["process_and_scope_closed"],
            "wrong physical arm",
        )
        sha = m["output_sha256"][".samples.jsonl"]
        log = verified(raw / "raw" / (name + ".samples.jsonl"), sha)
        d = a["native_clock_s"]
        # run_bounded starts t0 before Popen; wall is rounded to 1 ms.
        start = m["elapsed_s"] + 0.001 - d["decode32_s"]
        end = d["prefix_s"] + d["prefill153_s"] + d["decode32_s"]
        rows = [json.loads(line) for line in log.splitlines()]
        inside = [
            r["gpu"]["used_mib"]
            for r in rows
            if r["elapsed_s"] - 0.001 - r["collection_s"] > start and r["elapsed_s"] + 0.001 < end
        ]
        peak = m["maxima"]["gpu_used_mib"]
        c294.require(
            inside
            and max(r["gpu"]["used_mib"] for r in rows) == peak == a["maxima"]["gpu_used_mib"],
            "missing decode resource witness",
        )
        arms[name] = {
            "monitor_sha256": a["monitor_sha256"],
            "samples_sha256": sha,
            "global_peak_mib": peak,
            "decode_peak_witness_mib": max(inside),
            "decode_common_interior_s": [start, end],
            "interior_samples": len(inside),
            "interior_samples_at_peak": inside.count(max(inside)),
        }
    c294.require(len(arms) == 4 and family["status"] == "PASS_WARM_ROUTE_FAMILY", "four arms")
    peak = max(a["decode_peak_witness_mib"] for a in arms.values())
    stop = policy["gpu"]["memory_stop_total_mib"]
    slack = (stop - peak) * MIB
    c294.require(slack.is_integer() and slack > 0, "VRAM headroom")
    slack = int(slack)
    return {
        "arms": arms,
        "physical_total_mib": policy["gpu"]["total_mib"],
        "C55_memory_cap_bytes": policy["memory"]["cap_max_bytes"],
        "R0_memory_high_max_bytes": 20 << 30,
        "stop_total_mib": stop,
        "headroom_bytes": slack,
        "expert_weight_bytes": WEIGHT_BYTES,
        "k_at_sampled_peak": slack // WEIGHT_BYTES,
        "k_with_one_extra_mib": (slack + MIB) // WEIGHT_BYTES,
        "r5_policy_sha256": lock["sha256"],
        "family_sha256": FAMILY_SHA,
    }


def scores(groups):
    out = Counter()
    for ids, weight in groups:
        c294.require(len(ids) == len(set(ids)) == 4 and weight >= 0, "invalid cohort")
        for expert in ids:
            out[expert] += weight
    return sorted(out.values(), reverse=True)


def test_certificate():
    groups = [((0, 1, 2, 3), 10), ((0, 1, 4, 5), 9), ((0, 1, 2, 4), 1)]
    for k in range(7):
        best = max(
            sum(w for ids, w in groups if set(ids) <= set(s))
            for s in itertools.combinations(range(6), k)
        )
        c294.require(4 * best <= sum(scores(groups)[:k]), "invalid toy bound")
    try:
        scores([((0, 0, 1, 2), 1)])
    except ValueError:
        return
    raise ValueError("accepted repeated expert")


def arm(raw, entries, name, k):
    case = name.split("-")[1]
    refs = {}

    def entry(filename):
        key = f"{name}.native/{filename}"
        item = entries[key]
        refs[filename] = item["sha256"]
        return verified(raw / key, item["sha256"], item["bytes"])

    native = json.loads(entry("result.json"))
    c294.require(
        native["case"] == case and native["profile"] == "R0" and native["trace"], "C294 arm"
    )
    content = entry("events.tsv").splitlines()
    c294.require(content[0].decode() == c294.HEADER, "journal schema")
    markers, groups, sizes = {}, {}, set()
    current = None
    for line in content[1:]:
        kind, stamp, call, route, layer, expert, _, _, _, size, rows = map(int, line.split())
        if not call:
            continue
        key = (call, layer, kind)
        if kind in (1, 2, 15, 16):
            c294.require(key not in markers, "duplicate marker")
            markers[key] = stamp
        if kind == 2:
            current = (call, layer, route)
            groups[call, layer] = []
            c294.require(rows == 1 and route > 0, "multirow decode")
        elif kind == 3:
            c294.require(current == (call, layer, route), "foreign route")
            groups[call, layer].append(expert)
        elif kind == 6:
            sizes.add(size)
    c294.require(sizes == {WEIGHT_BYTES // 3}, "component bytes")
    ordered = ((call, layer, PROMPT[case] + call - 1, ids) for (call, layer), ids in groups.items())
    rank_sha = check_witness(case, ordered)
    weighted = []
    previous_end = markers[1, -1, 15]
    for call in range(1, 33):
        begin, end = (markers[call, -1, kind] for kind in (15, 16))
        routers = [markers[call, layer, 2] for layer in range(36)]
        boundaries = [markers[call, layer, 1] for layer in range(25)] + [routers[25]]
        c294.require(
            previous_end <= begin < end
            and begin <= boundaries[0]
            and all(a <= b for a, b in itertools.pairwise(routers))
            and routers[-1] <= end,
            "step chain",
        )
        previous_end = end
        for layer, (left, right) in enumerate(itertools.pairwise(boundaries)):
            c294.require(left <= routers[layer] <= right, "feature or successor order")
            ids = tuple((layer, expert) for expert in groups[call, layer])
            weighted.append((ids, right - left + 1))
    c294.require(len(weighted) == 32 * 25, "CPU cohort count")
    ranking = scores(weighted)
    count_ranking = scores((ids, 1) for ids, _ in weighted)
    window = markers[32, -1, 16] - markers[1, -1, 15] - 1
    clock = native["decode32_s"]
    c294.require(0 < window <= clock * US + 2, "nested clocks incompatible")
    # The synchronized source endpoints enclose the journal's inner endpoints.
    savings4 = sum(ranking[:k])
    remaining4 = 4 * window - savings4
    c294.require(remaining4 > 0, "invalid relaxation")
    first_k = next(
        (
            i
            for i, s in enumerate(itertools.accumulate(ranking), 1)
            if 6 * (4 * window - s) <= 128 * US
        ),
        None,
    )
    return {
        "source_sha256": refs,
        "ordered_rank_sha256": rank_sha,
        "steps": 32,
        "CPU_cohorts": len(weighted),
        "distinct_layer_expert_keys": len(ranking),
        "native_decode32_s": clock,
        "journal_decode32_floor_us": window,
        "CPU_intervals_us_before_rounding": sum(w - 1 for _, w in weighted),
        "complete_cohorts_ceiling": sum(count_ranking[:k]) // 4,
        "saved_quarter_us_ceiling": savings4,
        "saved_seconds_ceiling": savings4 / (4 * US),
        "remaining_quarter_us_floor": remaining4,
        "remaining_seconds_floor": remaining4 / (4 * US),
        "supplied_steps_per_second_ceiling": 128 * US / remaining4,
        "first_k_passing_relaxation": first_k,
        "status": "NO_GO_SIX_SUPPLIED" if 6 * remaining4 > 128 * US else "BOUND_TOUCHES_TARGET",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-dir", type=Path, required=True, help="C294 raw root")
    p.add_argument("--wrt-family-dir", type=Path, required=True, help="WRT40 family root")
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (256 * MIB, 256 * MIB))
    signal.alarm(60)
    start = time.monotonic()
    a.new_output_dir.mkdir(exist_ok=False)
    try:
        verified(HERE / "protocol.md", PROTOCOL)
        test_certificate()
        vram = capacity(a.wrt_family_dir)
        manifest = json.loads(verified(c294.MANIFEST, c294.MANIFEST_SHA))
        entries = {item["path"].split("/raw/")[1]: item for item in manifest["files"]}
        results = {
            name: arm(a.raw_dir, entries, name, vram["k_with_one_extra_mib"]) for name in c294.NAMES
        }
        out = {
            "evidence": "TRACE_DERIVED_CONDITIONAL_FORMAL_BOUND",
            "status": "NO_GO"
            if all(a["status"] == "NO_GO_SIX_SUPPLIED" for a in results.values())
            else "INCONCLUSIVE",
            "protocol_sha256": PROTOCOL,
            "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "c294_manifest_sha256": c294.MANIFEST_SHA,
            "capacity": vram,
            "arms": results,
            "wall_s": time.monotonic() - start,
            "rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }
    except Exception as error:
        (a.new_output_dir / "FAIL.json").write_text(json.dumps({"error": str(error)}) + "\n")
        raise
    s = json.dumps(out, indent=2, allow_nan=False) + "\n"
    with (a.new_output_dir / "receipt.json").open("x") as output:
        output.write(s)
    print(out["status"])


if __name__ == "__main__":
    main()
