"""Partition sealed C281 DEBUG producer intervals and bound conditional B3 prices."""

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
CLASSES = ("ordinary", "proposal_anchor", "skipped")
VERIFY = "494101d84e2696670bf59589768c3a7208db1c6b0b5ac1f6f914d3d9f264f08d"
B3 = "649bc3fe8f9e6469ab5cf7519ded4c5cb7d684cf36c792ca2a4b5eba018a7cbf"
CAPTURE = "8825a62338b9aebf913b3dc676dfb5b17ffa98885604e5f12091a3d47cae5f3a"


def check(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def pinned_json(path, expected):
    check(sha(path) == expected, "file digest: " + path.name)
    return json.loads(path.read_bytes(), parse_float=Decimal)


def stats(ticks, labels):
    durations = [b - a for a, b in zip(ticks[:-1], ticks[1:], strict=True)]
    n = len(labels)
    check(n <= len(durations) and min(durations) > 0, "producer timestamp order")
    sorted_window = sorted(durations[:n])
    result = {}
    for key in CLASSES:
        values = [d for d, label in zip(durations[:n], labels, strict=True) if key == label]
        k = len(values)
        result[key] = dict(
            count=k,
            sum_us=sum(values),
            mean_us=sum(values) / k if k else None,
            min_us=min(values, default=None),
            max_us=max(values, default=None),
            same_count_permutation_min_us=sum(sorted_window[:k]),
            same_count_permutation_max_us=sum(sorted_window[n - k :]) if k else 0,
        )
    check(sum(v["sum_us"] for v in result.values()) == ticks[n] - ticks[0], "partition")
    return result


def envelope(durations, selected, scale, jitter_us):
    """Independent endpoint lags cancel inside each consecutive selected run."""
    runs = sum(on and (j == 0 or not selected[j - 1]) for j, on in enumerate(selected))
    amount = scale * sum(d for d, on in zip(durations, selected, strict=True) if on)
    width = runs * (jitter_us + 4)
    return max(0, amount - width), amount + width


def constrained(durations, selected, native, scale, jitter_us):
    lo, hi = envelope(durations, selected, scale, jitter_us)
    c_lo, c_hi = envelope(durations, [not on for on in selected], scale, jitter_us)
    return [max(lo, native - c_hi, 0), min(hi, native - c_lo, native)]


def prices(window, ordinary, anchors, count, complete):
    budget = {}
    targets = {"reduce_15pct": [0.85 * t for t in window]}
    if complete:
        targets["six_tps"] = [47_000_000 / 6] * 2
    for key, (low, high) in targets.items():
        total = [low - ordinary[1], high - ordinary[0]]
        budget[key] = dict(
            total_verification_and_overhead_us=total,
            mean_per_proposal_us=[v / count for v in total],
            ratio_to_proposal_anchor_us=(
                [total[0] / anchors[1], total[1] / anchors[0]]
                if anchors[0] > 0 and total[0] >= 0
                else None
            ),
            headroom_if_b3_costs_its_anchor_us=[total[0] - anchors[1], total[1] - anchors[0]],
        )
    return budget


def analysis(ticks, feeds, labels, native):
    n = len(labels)
    durations = [b - a for a, b in zip(ticks[:-1], ticks[1:], strict=True)]
    check(0 < n <= len(durations), "nonempty window")
    summary = {}
    for key, cuts in (("sample", ticks), ("feed_terminal_sample", feeds + [ticks[-1]])):
        parts = stats(cuts, labels)
        elapsed = cuts[n] - cuts[0]
        ordinary = [parts["ordinary"]["sum_us"]] * 2
        anchor = [parts["proposal_anchor"]["sum_us"]] * 2
        summary[key] = dict(
            parts=parts,
            span_us=elapsed,
            producer_proxy_prices=prices(
                [elapsed] * 2,
                ordinary,
                anchor,
                labels.count("proposal_anchor"),
                n == len(durations),
            ),
        )
    windows = []
    for scale in (0.999, 1, 1.001):
        for jitter in (0, 1000, 10000):
            lo, hi = envelope(durations, [True] * len(durations), scale, jitter)
            scenario = dict(scale=scale, endpoint_lag_us=jitter, compatible=lo <= native <= hi)
            if scenario["compatible"]:

                def get(mask, scale=scale, jitter=jitter):
                    bounds = constrained(durations, mask, native, scale, jitter)
                    check(bounds[0] <= bounds[1], "empty scenario interval")
                    return bounds

                partition = {}
                for item in CLASSES:
                    partition[item] = get(
                        [p < n and labels[p] == item for p in range(len(durations))]
                    )
                window = get([p < n for p in range(len(durations))])
                scenario.update(
                    class_us=partition,
                    window_us=window,
                    prices=prices(
                        window,
                        partition["ordinary"],
                        partition["proposal_anchor"],
                        labels.count("proposal_anchor"),
                        n == len(durations),
                    ),
                )
            windows.append(scenario)
    return dict(
        position_count=n,
        boundary_proxies=summary,
        sensitivity=windows,
        unconditional_proper_subset_native_us=[0, native],
    )


def clock_us(parts):
    minutes, seconds, ms, us = parts
    return ((minutes * 60 + seconds) * 1000 + ms) * 1000 + us


def main_result(a):
    git_root = HERE.parents[4]

    def git(*args):
        return subprocess.check_output(["git", "-C", git_root, *args], text=True).strip()

    check(not git("status", "--porcelain"), "measurement checkout dirty")
    v = module("step_cost_native_ids", PARENT / "verify.py")
    fixture = module("step_cost_b3_trace", PARENT / "b3_fixture/run.py")
    verified = pinned_json(PARENT / "evidence/verified.json", VERIFY)
    old_b3 = pinned_json(PARENT / "evidence/b3.json", B3)
    pinned_json(a.verified / "receipt.json", VERIFY)
    cap = pinned_json(a.capture / "receipt.json", CAPTURE)
    check(
        verified["status"] == "PASS_TWO_NATURAL_SAMPLED_TRAJECTORIES"
        and verified["capture_receipt_sha256"] == CAPTURE
        and old_b3["verified_sha256"] == VERIFY,
        "source authority",
    )
    source = {
        **v.SOURCE,
        "ggml/src/ggml.c": "ef2a64f06c900993396612ab2bfb98238d5ea931abbc938ddb0c72d31a0bd043",
    }
    for name, digest in source.items():
        check(sha(a.backend / name) == digest, "C269 source: " + name)
    check(sha(PARENT / "verify.py") == verified["program_sha256"], "verifier source")
    raw = a.capture / "raw"
    stderr = raw / cap["native_ids"]["raw_stderr_file"]
    check(
        sha(stderr) == verified["stderr_sha256"] == cap["native_ids"]["stderr_sha256"],
        "logger digest",
    )
    log = stderr.read_bytes()
    series = v.trajectories(log)
    all_events = list(v.events(log))
    tasks = [task for _, task, event in all_events if event[0] == "start"]
    rule = fixture.python_rule()
    refs = verified["capture_turn_files_sha256"]
    report = []
    for i, (rows, task) in enumerate(zip(series, tasks, strict=True), 1):
        label = f"T{i}"
        target = [value for value, _ in rows]
        ids = a.verified / f"{label}-sampled.i32"
        seal = verified["turns"][i - 1]
        check(
            sha(ids) == seal["sampled_ids_sha256"]
            and ids.read_bytes() == v.ids_bytes(target)
            and seal["unique_final_eog"],
            "authenticated sample trajectory",
        )
        subset = [(clock_us(clk), e) for clk, owner, e in all_events if owner == task]
        ticks = [t for t, e in subset if e[0] == "sample"]
        feeds = [t for t, e in subset if e[0] == "feed"]
        check(
            len(ticks) == len(feeds) + 1 == len(target)
            and all(left <= f < r for left, f, r in zip(ticks[:-1], feeds, ticks[1:], strict=True)),
            "interleaved, advancing producer clock",
        )
        check(all(r > left for left, r in zip(ticks[:-1], ticks[1:], strict=True)), "sample clock")
        name = f"{label}-result.json"
        timings = pinned_json(raw / name, refs[name])["timings"]
        native_us = Decimal(timings["predicted_ms"]) * 1000
        check(
            native_us > 0 and int(native_us) == native_us and timings["predicted_n"] == len(target),
            "native duration/count",
        )
        native = int(native_us)
        journal = raw / f"{label}-request.jsonl"
        check(sha(journal) == refs[journal.name], "transport witness")
        timed = set()
        for line in journal.read_bytes().splitlines():
            row = json.loads(line)
            if row["kind"] != "SSE_FRAGMENT":
                continue
            frame = row["fragment"].strip()
            if frame.startswith("data: {"):
                parsed = json.loads(frame[6:])
                for node in (parsed, parsed.get("__verbose", {})):
                    item = node.get("timings", {})
                    if isinstance(item, dict) and item.get("predicted_ms") is not None:
                        timed.add(item.get("predicted_n"))
        # A complete native timing witness would justify a separate measurement
        # of identified cumulative sampler times, rather than a logger proxy.
        check(
            not set(range(1, len(target) + 1)).issubset(timed),
            "new native per-ID timings require review",
        )
        entry = dict(
            turn=label,
            samples=len(ticks),
            feed_echoes=len(feeds),
            native_predicted_us=native,
            producer_span_us=ticks[-1] - ticks[0],
            producer_minus_native_us=ticks[-1] - ticks[0] - native,
            native_timed_counts_in_sse=sorted(timed, key=str),
        )
        if i == 2:
            name = "T2-input.json"
            prompt = pinned_json(raw / name, refs[name])["official_ids"]
            check(v.digest(v.ids_bytes(prompt)) == old_b3["prompt_i32_sha256"], "prompt digest")
            entry["windows"] = []
            for end, declared in zip((32, 46), old_b3["windows"], strict=True):
                actions = fixture.trace(rule, prompt, target, end)
                reference = rule.replay(prompt, target[: end + 1], 2, 2)
                check(all(declared[k] == val for k, val in reference.items()), "sealed rule totals")
                labels = []
                for action in actions:
                    check(len(labels) == action["position"], "causal action position")
                    labels.append("ordinary" if action["ar"] else "proposal_anchor")
                    labels.extend(["skipped"] * (action["emitted"] - 1))
                check(
                    [labels.count(k) for k in CLASSES]
                    == [declared[k] for k in ("ordinary", "proposals", "fewer_calls")]
                    and len(labels) == end,
                    "class conservation",
                )
                entry["windows"].append(analysis(ticks, feeds, labels, native))
        report.append(entry)
    return dict(
        status="REPRODUCED_DEBUG_PRODUCER_INTERVALS",
        native_position_time="INCONCLUSIVE",
        target_B3_cost="NOT_RUN",
        turns=report,
        commit=git("rev-parse", "HEAD"),
        tree=git("rev-parse", "HEAD^{tree}"),
        backend_sources=source,
        inputs_sha256=dict(verified=VERIFY, capture=CAPTURE, b3=B3),
        analysis_sha256=sha(Path(__file__)),
        protocol_sha256=sha(HERE / "protocol.md"),
        model_forwards=0,
        gpu_used=False,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("capture", "verified", "backend", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = main_result(a)
    except Exception as exc:
        result = dict(
            status="FAIL_PRESERVED",
            reason=str(exc) if type(exc) is ValueError else type(exc).__name__,
        )
    with (a.new_output_dir / "receipt.json").open("x") as dest:
        json.dump(result, dest, indent=2, sort_keys=True, allow_nan=False)
        dest.write("\n")
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
