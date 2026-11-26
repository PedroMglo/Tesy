"""Measure seven stock autoregressive step intervals after the exact first Aster prompt."""

import argparse
import hashlib
import http.client
import math
import re
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parent
sys.path.insert(0, str(QUAL))
from aster_cache_geometry.verify import probe_inputs  # noqa: E402
from aster_split import probe as split  # noqa: E402
from c2_server_run import json_bytes  # noqa: E402
from two_turn_pair import digest, read  # noqa: E402

require = split.require
PROTO = "2c58d2ceebb777e1748457022c08f3aaf42f0e99fdfa7eac1ca15fadb7e7027b"


def nonnegative(x):
    return type(x) in (float, int) and math.isfinite(x) and x >= 0


def fixed_run(path, expected):
    require(re.fullmatch("[a-f0-9]{64}", expected), "fixed receipt digest required")
    r = read(path, expected)
    require(
        r["status"] == "PASS_STOCK_FULL_SWA_FIXED_122_313"
        and r["returncode"] == 0
        and r["child_gone"] is True
        and r["http_requests_sent"] == 2
        and r["server_starts"] == 1,
        "prior fixed probe did not pass",
    )
    rows = r["after_ready"]["requests"]
    require(
        [(x["cache_n"], x["prompt_n"], x["predicted_n"]) for x in rows]
        == [(0, 123, 1), (122, 313, 1)],
        "fixed split not observed",
    )
    second = rows[-1]
    require(
        all(nonnegative(second[k]) for k in ("prompt_ms", "predicted_ms", "client_s")),
        "invalid fixed phase clocks",
    )
    return second


def trajectory(raw, client_s, length, cached):
    require(nonnegative(client_s), "client clock")
    terminal = None
    tokens = {}
    stamps = {}
    for line in raw.splitlines():
        if not line.startswith(b"data: "):
            continue
        require(terminal is None, "data after native stop")
        event = split.strict_json(line[6:])
        n = event["tokens_predicted"]
        require(
            type(n) is int
            and 1 <= n <= 8
            and type(event["tokens_evaluated"]) is int
            and event["tokens_evaluated"] == length,
            "wrong request counts",
        )
        t = event["timings"]
        require(
            all(type(t[key]) is int for key in ("predicted_n", "prompt_n", "cache_n"))
            and t["predicted_n"] == n
            and t["prompt_n"] == length - cached
            and t["cache_n"] == cached
            and nonnegative(t["predicted_ms"])
            and nonnegative(t["prompt_ms"]),
            "wrong per-token timings",
        )
        if event["stop"] is True:
            require(
                event["truncated"] is False
                and event["id_slot"] == 0
                and event["tokens"] == []
                and event["stop_type"] in ("limit", "eos"),
                "invalid native terminal",
            )
            terminal = event
        else:
            require(
                event["stop"] is False
                and len(event["tokens"]) == 1
                and n not in tokens
                and (not tokens or n > max(tokens))
                and type(event["tokens"][0]) is int
                and 0 <= event["tokens"][0] < 201088,
                "invalid per-token record",
            )
            tokens[n] = event["tokens"][0]
            stamps[n] = t["predicted_ms"] / 1000
    require(terminal is not None, "missing native stop")
    n = terminal["tokens_predicted"]
    t = terminal["timings"]
    require(
        max(stamps, default=0) <= n
        and (n not in stamps or math.isclose(stamps[n], t["predicted_ms"] / 1000, rel_tol=1e-12)),
        "terminal time or count changed",
    )
    observed = {
        "tokens": n,
        "observed_step_endpoints": len(stamps),
        "stop_type": terminal["stop_type"],
        "server_prompt_s": t["prompt_ms"] / 1000,
        "server_generation_s": t["predicted_ms"] / 1000,
        "client_wall_s": client_s,
        "observed_token_stream_sha256": digest(list(tokens.items())),
    }
    if n < 8:
        require(terminal["stop_type"] == "eos", "early output without EOS")
        return (
            dict(observed, decision="INCONCLUSIVE_EARLY_STOP", projected_historical_s=None),
            list(tokens.values()),
            [],
        )
    if list(stamps) != list(range(1, 9)):
        return (
            dict(
                observed, decision="INCONCLUSIVE_MISSING_TOKEN_CLOCK", projected_historical_s=None
            ),
            list(tokens.values()),
            [],
        )
    steps = [stamps[i] - stamps[i - 1] for i in range(2, 9)]
    require(min(steps) > 0, "nonpositive time between tokens")
    return observed, list(tokens.values()), steps


def parse(raw, client_s, fixed):
    observed, _, steps = trajectory(raw, client_s, 121, 0)
    if not steps:
        return observed
    residual0 = max(0.0, client_s - observed["server_prompt_s"] - observed["server_generation_s"])
    residual1 = max(0.0, fixed["client_s"] - (fixed["prompt_ms"] + fixed["predicted_ms"]) / 1000)
    base = observed["server_prompt_s"] + fixed["prompt_ms"] / 1000 + residual0 + residual1
    band = {"favorable": min(steps), "mean": statistics.mean(steps), "unfavorable": max(steps)}
    cost = {k: base + 791 * v for k, v in band.items()}
    decision = "INCONCLUSIVE_BUDGET"
    if cost["favorable"] > 1800:
        decision = "NO_GO_STOCK_REFERENCE_BUDGET"
    elif cost["unfavorable"] <= 1800:
        decision = "GO_CONSIDER_BOUNDED_PAIR"
    return dict(
        observed,
        decision=decision,
        step_s=steps,
        seconds_per_step=band,
        historical_nonfirst_steps=791,
        estimated_fixed_s=base,
        client_overhead_s=[residual0, residual1],
        projected_historical_s=cost,
        admissible_s_per_step=(1800 - base) / 791,
        projected_1532_steps_s={k: base + 1532 * v for k, v in band.items()},
    )


def listener_port(raw):
    ports = set(
        re.findall(
            r"listening on http://127\.0\.0\.1:(\d+)\b",
            (raw / "server.log").read_text(errors="replace"),
        )
    )
    require(len(ports) == 1, "missing unique listener")
    return int(ports.pop())


def exchange(pid, raw, cancelled, progress, ids, stem, port, deadline):
    require(not cancelled.is_set(), "cancelled by monitor")
    split.owned_listener(pid, port)
    payload = json_bytes(
        {
            "prompt": ids,
            "n_predict": 8,
            "id_slot": 0,
            "cache_prompt": True,
            "temperature": 0,
            "seed": 42,
            "stream": True,
            "return_tokens": True,
            "timings_per_token": True,
        }
    )
    split.save(raw / f"{stem}.request.json", payload)
    before = time.monotonic()
    remaining = deadline - before
    require(remaining > 0, "budget expired")
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=remaining)
    try:
        progress["http_requests_sent"] += 1
        progress["sampling_tokens_requested"] += 8
        conn.request("POST", "/completion", payload, {"Content-Type": "application/json"})
        response = conn.getresponse()
        require(response.status == 200, "non-200 HTTP response")
        total = 0
        with (raw / f"{stem}.sse").open("xb") as f:
            while True:
                require(
                    not cancelled.is_set() and time.monotonic() <= deadline,
                    "budget expired",
                )
                line = response.readline(131073)
                if not line:
                    break
                total += len(line)
                require(
                    len(line) <= 131072 and total + len(payload) <= 1024 * 1024,
                    "private byte budget",
                )
                f.write(line)
        elapsed = time.monotonic() - before
    finally:
        conn.close()
    data = (raw / f"{stem}.sse").read_bytes()
    require(before + elapsed <= deadline and not cancelled.is_set(), "budget expired")
    return data, elapsed, hashlib.sha256(payload).hexdigest()


class Probe:
    run_id = "stock-aster-full-budget"
    pass_status = "PASS_STOCK_ASTER_COST_OBSERVATION_ONLY"
    protocol_path = HERE / "protocol.md"
    timeout_s = 240

    def __init__(self, history, receipt, expected):
        require(
            hashlib.sha256(self.protocol_path.read_bytes()).hexdigest() == PROTO,
            "changed budget protocol",
        )
        self.fixed = fixed_run(receipt, expected)
        self.fixed_sha = expected
        self.ids = probe_inputs(history)[1][:121]
        manifest = read(QUAL / "two_turn_evidence_r1/manifest.json")["input_manifest"]["turns"][0]
        require(
            digest(self.ids) == manifest["prompt_ids_sha256"], "wrong first official C133 input"
        )

    def run(self, pid, raw, cancelled, progress):
        port = listener_port(raw)
        data, elapsed, request_sha = exchange(
            pid,
            raw,
            cancelled,
            progress,
            self.ids,
            "budget",
            port,
            time.monotonic() + self.timeout_s,
        )
        return parse(data, elapsed, self.fixed) | {
            "fixed_receipt_sha256": self.fixed_sha,
            "protocol_sha256": PROTO,
            "input_sha256": digest(self.ids),
            "request_sha256": request_sha,
            "sse_sha256": hashlib.sha256(data).hexdigest(),
        }


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--historical-results", type=Path, required=True)
    ap.add_argument("--split-receipt", type=Path, required=True)
    ap.add_argument("--split-sha256", required=True)
    sys.path.insert(0, str(QUAL / "aster_full_ready"))
    from loader import cli_for

    if "--help" in sys.argv:
        ap.print_help()
        cli_for()
        return
    a, rest = ap.parse_known_args()
    sys.argv[1:] = rest
    cli_for(probe=Probe(a.historical_results, a.split_receipt, a.split_sha256))


if __name__ == "__main__":
    main()
