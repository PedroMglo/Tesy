"""Price the authenticated natural request across all admissible monitor clock offsets."""

import argparse
from collections import Counter
from decimal import ROUND_CEILING
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
S = run_path(str(HERE / "review.py"))
P = S["P"]
BASE = P["QUAL"] / "nvme_conversation/phase_reads/screen.py"
need, sha = P["need"], P["sha"]
FAMILY = "8fc33c06313d1a5888fb1bbb75c9c95cef361382fc6bfd127b0781b4962d602b"
CONTEXT = "b011ddd38926ad480d84954fe7679f63327118f47bfa8b98da7b3117ac7db4af"
CLOCK = "c5df4df515875916f4334c40817b29593d4ff32e0d2ee042715740877ec568a7"
PROTOCOL = "fc3cb59601de0d9c05d62018e52ab360d11e73e39a248d64e5cc0467da44698a"
PRODUCT = "15c8a4cdfaa43107af5bdb5699ae783324d8c773c4ce820d9f3c38926d9598a9"
RATE = 4_500_000_000


def samples_for(bounds, rows, pid, origin):
    samples = []
    fds = Counter()
    ns = bounds["ns"]
    for row in rows:
        need(row["pid"] == pid["pid"] and row["process_identity"] == pid, "PID changed")
        fd = row["model_fds"]
        need(fd["direct"] == 0 and fd["open"] == fd["buffered"], "unexpected model FD")
        fds[fd["open"]] += 1
        t = origin + ns(row["elapsed_s"])
        c = tuple(row["proc"][k] for k in bounds["KEYS"])
        need(all(type(v) is int and v >= 0 for v in c), "invalid process counter")
        sample = bounds["Sample"](
            t - 500_001 - ns(row["collection_s"], ROUND_CEILING), t + 500_001, c
        )
        if samples:
            prev = samples[-1]
            need(
                prev.hi < sample.lo and all(a <= b for a, b in zip(prev.counters, c, strict=True)),
                "sample chronology or reset",
            )
        samples.append(sample)
    need(max(fds) == 7 and len(samples) >= 2, "missing buffered server samples")
    return samples, fds


def turn(bounds, folder, i, samples, shift):
    raw = folder / "raw"
    ns, margin = bounds["ns"], bounds["MARGIN"]
    row = bounds["read"](raw / f"T{i}-result.json")
    last = bounds["lines"](raw / f"T{i}-request.jsonl")[-1]
    s, e = (ns(row[k]) for k in ("request_started_monotonic", "request_ended_monotonic"))
    v = ns(last["monotonic_s"])
    p, d = (ns(row["timings"][k] / 1000) for k in ("prompt_ms", "predicted_ms"))
    first = ns(row["stream_metrics"]["first_final_content_chunk_s"])
    need(s + p + d <= e <= v and row["accepted"] and last["accepted"], "phase chronology")
    phases = {
        "prefill": bounds["Phase"](s - margin, e - p - d + margin, s + p - margin, e - d + margin),
        "decode": bounds["Phase"](s + p - margin, e - d + margin, s + p + d - margin, e + margin),
        "first_final": bounds["between"](s, s + first),
        "valid": bounds["between"](s, v),
    }
    return dict(
        turn=i,
        prefill_ns=p,
        decode_ns=d,
        first_final_ns=first,
        server_predicted_n=row["timings"]["predicted_n"],
        transport_outside_native_ns=e - s - p - d,
        phases={k: bounds["extrema"](samples, phase, shift) for k, phase in phases.items()},
    )


def price(prefill, budget, ns):
    if budget <= 0:
        return dict(decision="NO_GO_NONPOSITIVE_TIME_BUDGET", prefill_budget_ns=budget)
    cap = (RATE * budget + ns - 1) // ns
    if prefill["min"] > cap:
        decision = "NO_GO_SERVICE_FIXED"
    elif prefill["max"] is not None and prefill["max"] <= cap:
        decision = "HEADROOM_BYTES_ONLY"
    else:
        decision = "INCONCLUSIVE"
    return dict(
        decision=decision,
        prefill_budget_ns=budget,
        available_B_ceil=cap,
        minimum_removed_or_advanced_B=max(0, prefill["min"] - cap),
        minimum_necessary_Bps_floor=prefill["min"] * ns // budget,
        minimum_missing_ns_floor=max(0, prefill["min"] * ns // RATE - budget),
    )


def analyze(family, backend):
    need(
        sha(HERE / "phase-protocol.md") == PROTOCOL
        and sha(BASE) == "94548f7024daef5626e383fe1839e18b750cb75cffc0031f628af23fbe22ff47"
        and sha(HERE / "result.json") == PRODUCT,
        "research authorities",
    )
    bounds = run_path(str(BASE))
    expected = S["review"](SimpleNamespace(family=family, family_sha256=FAMILY))
    need(expected == P["CON"]["load"](HERE / "result.json"), "product review differs")
    need(
        P["B"]["git"](backend, "rev-parse", "HEAD") == P["B"]["PIN"]
        and sha(backend / "examples/server/server-context.cpp") == CONTEXT
        and sha(backend / "ggml/src/ggml.c") == CLOCK
        and all(sha(P["REPO"] / k) == v for k, v in bounds["SOURCE"].items()),
        "clock sources",
    )
    raw = family / "raw"
    read = bounds["read"]
    unit = read(family / "receipt.json")["unit"]
    launch = read(raw / (unit + ".launch.json"))
    monitor = read(raw / (unit + ".json"))
    client = read(family / "client-receipt.json")
    pid = client["process_identity"]
    need(
        pid == launch["process_identity"] == monitor["process_identity"]
        and sha(raw / (unit + ".launch.json")) == client["launch_sha256"],
        "client/monitor launch",
    )
    origin = launch["start_inventory"]["popen_invoked_monotonic_ns"]
    shift = bounds["ns"](client["ready_monotonic"], ROUND_CEILING) + bounds["MARGIN"] - origin
    observations = bounds["lines"](raw / (unit + ".samples.jsonl"))
    samples, fds = samples_for(bounds, observations, pid, origin)
    turns = [turn(bounds, family, i, samples, shift) for i in (1, 2)]
    t = turns[1]
    ns = bounds["NS"]
    budget = t["prefill_ns"] + 10 * ns - t["first_final_ns"] + t["decode_ns"]
    prefill = t["phases"]["prefill"]["counters"]["read_bytes"]
    return dict(
        family_sha256=FAMILY,
        protocol_sha256=PROTOCOL,
        assumed_Bps=RATE,
        epoch_width_ns=shift,
        samples=len(samples),
        open_buffered_fds=dict(fds),
        turns=turns,
        at_6_toks=price(prefill, budget - t["server_predicted_n"] * ns // 6, ns),
        instantaneous_decode=price(prefill, budget, ns),
        first_final_floor_zero_decode_ns=t["first_final_ns"] - t["decode_ns"],
        first_final_floor_zero_prefill_ns=t["first_final_ns"] - t["prefill_ns"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("family", "backend", "new-output-dir"):
        parser.add_argument("--" + k, required=True, type=Path)
    a = parser.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    result = analyze(a.family, a.backend)
    S["S"]["save"](a.new_output_dir / "result.json", result)
    print(result["at_6_toks"]["decision"], result["instantaneous_decode"]["decision"])
