"""Bound mandatory C135 READ time when every non-read operation becomes free."""

import argparse
import json
import resource
import signal
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "prefill_dispatch"))
import dispatch  # noqa: E402

require = dispatch.require
SOURCE = "23e701fec3d548a7b5faeb7ac854c4284830758f57a187b5db34e5a52b8b80c8"
PROTOCOL = "178dfd58bbf4df15964e8603cc7401189c182d97ced86770e346a8aedc987c15"
ANALYSIS = "2a331bafe266decf08112fe5166c6801738fdb6666a3cfe0e26d59f2346bc056"


def small_call(rows, critical):
    """Call 5 is non-wave. Every miss has its own reservation and synchronous layer wait."""
    parts = dispatch.component_times(rows, critical.generation)
    scopes = []
    for layer in sorted({r["layer"] for r in rows if r["kind"] == "DEMAND"}):
        layer_rows = [r for r in rows if r["layer"] == layer]
        demands = [r for r in layer_rows if r["kind"] == "DEMAND"]
        require(all(r["wave"] == -1 and r["n_tokens"] in (1, 5) for r in demands), "non-wave")
        require(len({r["expert"] for r in demands}) == len(demands), "duplicate demand")
        absent = {r["expert"]: r for r in demands if r["state"] != 2}
        queues = [r for r in layer_rows if r["kind"] == "ENQUEUE"]
        require(all(r["state"] == 0 for r in absent.values()), "loading hit requires a join")
        require(len(queues) == len(absent) and {r["expert"] for r in queues} == set(absent),
                "missing or extra generation")
        if not queues:
            continue
        waits = [r for r in layer_rows if r["kind"] in {"WAIT_BEGIN", "WAIT_END"}]
        require([r["kind"] for r in waits] == ["WAIT_BEGIN", "WAIT_END"], "ambiguous wait")
        jobs = []
        for enqueue in queues:
            key = critical.generation(enqueue)
            reserved = [r for r in layer_rows if r["kind"] == "RESERVE"
                        and (r["expert"], r["slot"]) == key[1:3]]
            require(len(reserved) == 1 and absent[key[1]]["seq"] < reserved[0]["seq"]
                    < enqueue["seq"] < waits[0]["seq"], "demand/reserve/enqueue/wait order")
            jobs.append((key, enqueue["seq"], waits[1]["seq"], None, parts[key]))
        scopes.append({"begin": demands[0]["seq"], "end": waits[1]["seq"], "jobs": jobs})
    return scopes


def floor(rows, critical):
    require(rows[0]["kind"] == "CALL_BEGIN" and rows[-1]["kind"] == "CALL_END", "open call")
    call = rows[0]["call_id"]
    require((call, rows[0]["n_tokens"]) in ((1, 5), (2, 148)), "wrong input shape")
    scopes = small_call(rows, critical) if call == 1 else dispatch.build_scopes(rows, critical)[0]
    commits = critical.commit_bounds(rows)
    clocks = {r["seq"]: r["mono_us"] for r in rows}
    phases = defaultdict(dict)
    raw_reads = Counter()
    for r in rows:
        if r["kind"] in {"LOAD_BEGIN", "LOAD_END", "DEQUEUE"}:
            phases[critical.generation(r)][r["kind"]] = r
        if r["kind"] == "READ_END":
            raw_reads[critical.generation(r)] += 1
    checked = set()
    previous = rows[0]["seq"]
    total_read = adjusted = temporal_floor_fourths = max_chain = 0
    for scope in scopes:
        start, end = scope["begin"], scope["end"]
        require(previous <= start <= end and clocks[previous] <= clocks[start] <= clocks[end],
                "overlapping scopes")
        previous = end
        durations = []
        for key, release, deadline, _, part in scope["jobs"]:
            phase = phases[key]
            require(key not in checked and raw_reads[key] == 3, "three unique READ mandatory")
            checked.add(key)
            require(start <= release < phase["DEQUEUE"]["seq"]
                    <= phase["LOAD_BEGIN"]["seq"] < phase["LOAD_END"]["seq"]
                    <= deadline <= end, "worker escaped its consumer window")
            require(clocks[release] <= phase["LOAD_BEGIN"]["mono_us"]
                    and commits[key][0] <= deadline
                    and commits[key][2] <= clocks[deadline], "outside temporal deadline")
            # The three separate integer-clock spans may each overstate duration by up to 1 us.
            total_read += part["read"]
            durations.append(max(0, part["read"] - 3))
        require(durations, "empty scope")
        adjusted += sum(durations)
        longest = max(durations)
        max_chain = max(longest, max_chain)
        local_fourths = max(sum(durations), 4 * longest)
        require(local_fourths <= 4 * (clocks[end] - clocks[start] + 1), "local capacity")
        temporal_floor_fourths += local_fourths
    require(checked == set(phases) == set(raw_reads) == set(commits), "unmatched service")
    return dict(tokens=rows[0]["n_tokens"], jobs=len(checked), component_reads=3 * len(checked),
                cpu_jobs=sum(key[0] < 25 for key in checked), scopes_with_reads=len(scopes),
                observed_call_us=rows[-1]["mono_us"] - rows[0]["mono_us"],
                read_worker_us=total_read, global_capacity_floor_us=adjusted / 4,
                longest_serial_chain_us=max_chain, summed_scope_floor_us=temporal_floor_fourths / 4)


def run(trace, checkout):
    require(dispatch.digest(Path(dispatch.__file__)) == SOURCE, "changed dispatch helper")
    require(dispatch.digest(HERE / "protocol.md") == PROTOCOL, "changed protocol")
    require(trace.stat().st_size == 3603647 and dispatch.digest(trace) == dispatch.TRACE, "C135")
    analysis = HERE.parents[2] / "results/c135-slots40-warm153-trace-20260929T2205Z/analysis.json"
    require(dispatch.digest(analysis) == ANALYSIS, "changed C135 timing")
    critical, _ = dispatch.imports(checkout)
    critical.validate(trace)
    _, rows = critical.trace_rows(trace)
    arms = [floor([r for r in rows if r["call_id"] == call], critical) for call in (1, 2)]
    require(arms[0]["jobs"] + arms[1]["jobs"] == 1222, "whole prefill loads")
    server = json.loads(analysis.read_text())["server"]["trace_on"]
    server_us = round(server["warm_prefill_s"] * 1e6)
    return dict(classification="TRACE_DERIVED_FIXED_READ_SERVICE", protocol_sha256=PROTOCOL,
                trace_sha256=dispatch.TRACE, analysis_sha256=ANALYSIS, pr45_head=dispatch.PIN,
                pr45_source_sha256=dispatch.SOURCES, dispatch_sha256=SOURCE, calls=arms,
                server_prefill_us=server_us,
                server_minus_call_sum_us=server_us - sum(a["observed_call_us"] for a in arms),
                full_prefill_read_floor_us=sum(a["summed_scope_floor_us"] for a in arms))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--pr45-checkout", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (256 << 20, 256 << 20))
    signal.alarm(60)
    require(not args.new_output_dir.resolve().is_relative_to(args.trace.resolve().parent),
            "protect raw")
    args.new_output_dir.mkdir(parents=True, exist_ok=False)
    report = run(args.trace, args.pr45_checkout)
    pending = args.new_output_dir / "receipt.pending"
    pending.write_text(json.dumps(report, indent=2) + "\n")
    pending.replace(args.new_output_dir / "receipt.json")


if __name__ == "__main__":
    main()
