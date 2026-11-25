"""Stock E10 primer and fixed second-turn Aster eight-token timing probe."""

import argparse
import hashlib
import http.client
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parent
sys.path.insert(0, str(QUAL))
from aster_budget import probe as budget  # noqa: E402
from aster_split import probe as split  # noqa: E402

require = split.require
SPLIT_SHA = "ed55f7c2c5ec983d2c96b5c7ef1f4bd0740aed861bbe9d8661680486a65740b3"
T1_SHA = "b26808e96d641a78d132ba44804957be69b2e66f3adbbe23ab6eb4173c188e2d"
PROTO = "d4677c995650bd40a03a06369c3613ac404a94ca6b54680d6204cbe3d5894f62"


def primer(pid, raw, cancelled, progress, ids, port, deadline, request_hash):
    require(not cancelled.is_set(), "cancelled before primer")
    split.owned_listener(pid, port)
    body = split.json_bytes(
        dict(
            prompt=ids,
            n_predict=1,
            id_slot=0,
            cache_prompt=True,
            temperature=0,
            seed=42,
            stream=False,
            return_tokens=True,
        )
    )
    require(hashlib.sha256(body).hexdigest() == request_hash, "primer differs from sealed request")
    split.save(raw / "primer.request.json", body)
    before = time.monotonic()
    require(deadline > before, "expired primer")
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=deadline - before)
    try:
        progress["http_requests_sent"] += 1
        progress["sampling_tokens_requested"] += 1
        conn.request("POST", "/completion", body, {"Content-Type": "application/json"})
        response = conn.getresponse()
        data = response.read(256 * 1024 + 1)
        end = time.monotonic()
        split.save(raw / "primer.response.json", data)
        require(
            response.status == 200 and len(data) <= 256 * 1024 and len(body) + len(data) <= 2**20,
            "primer HTTP or byte cap",
        )
        require(end <= deadline and not cancelled.is_set(), "expired primer")
        fields = split.validated_counts(split.strict_json(data), 123, 0)
    finally:
        conn.close()
    return {
        **fields,
        "request_sha256": request_hash,
        "response_sha256": hashlib.sha256(data).hexdigest(),
        "client_s": end - before,
        "send_monotonic_s": before,
        "complete_monotonic_s": end,
    }


def project(observed, steps, primer_client_s):
    require(
        len(steps) == 7 and all(budget.nonnegative(x) and x > 0 for x in steps),
        "seven step durations",
    )
    require(
        budget.nonnegative(primer_client_s)
        and all(
            budget.nonnegative(observed[k])
            for k in ("client_wall_s", "server_prompt_s", "server_generation_s")
        ),
        "phase clocks",
    )
    first = observed["server_generation_s"] - sum(steps)
    require(first >= -1e-9, "negative first endpoint")
    first = max(0.0, first)
    overhead = max(
        0.0,
        observed["client_wall_s"] - observed["server_prompt_s"] - observed["server_generation_s"],
    )
    base = primer_client_s + observed["server_prompt_s"] + overhead + first
    band = {"favorable": min(steps), "mean": statistics.mean(steps), "unfavorable": max(steps)}
    estimate = {k: base + 451 * x for k, x in band.items()}
    decision = "INCONCLUSIVE_BUDGET"
    if estimate["favorable"] > 1800:
        decision = "NO_GO_FIXED_T2_BUDGET"
    elif estimate["unfavorable"] <= 1800:
        decision = "GO_FIXTURE_FIXED_T2_ONLY"
    return {
        "decision": decision,
        "primer_client_s": primer_client_s,
        "first_endpoint_s": first,
        "T2_client_overhead_s": overhead,
        "estimated_fixed_s": base,
        "historical_nonfirst_steps": 451,
        "step_s": steps,
        "seconds_per_step": band,
        "projected_historical_s": estimate,
        "admissible_s_per_step": (1800 - base) / 451,
        "projected_cap768_s": {k: base + 767 * x for k, x in band.items()},
    }


def first_emitted(raw):
    for line in raw.splitlines():
        if line.startswith(b"data: "):
            event = split.strict_json(line[6:])
            if event["stop"] is False and event["tokens_predicted"] == 1:
                return event["tokens"][0]
    return None


class Probe:
    run_id = "stock-aster-full-turn2-budget"
    pass_status = "PASS_STOCK_ASTER_FIXED_T2_COST_OBSERVATION_ONLY"
    timeout_s = 480
    protocol_path = HERE / "protocol.md"

    def __init__(self, history, prior_response):
        require(
            hashlib.sha256(self.protocol_path.read_bytes()).hexdigest() == PROTO, "protocol changed"
        )
        split_file = QUAL / "aster_split/physical-r1/receipt.json"
        budget.fixed_run(split_file, SPLIT_SHA)
        prior = budget.read(split_file, SPLIT_SHA)
        t1 = budget.read(QUAL / "aster_budget/physical-r1/receipt.json", T1_SHA)
        require(
            t1["status"] == "PASS_STOCK_ASTER_COST_OBSERVATION_ONLY"
            and t1["returncode"] == 0
            and t1["child_gone"]
            and t1["after_ready"]["fixed_receipt_sha256"] == SPLIT_SHA
            and t1["cap_bytes"] == prior["cap_bytes"] == 10 * 2**30
            and t1["build_receipt_sha256"] == prior["build_receipt_sha256"]
            and t1["effective_jinja_sha256"] == prior["effective_jinja_sha256"],
            "historical stock E10",
        )
        first, second = prior["after_ready"]["requests"]
        self.primer_hash = first["request_sha256"]
        self.t2_hash = second["response_sha256"]
        require(prior_response.stat().st_size <= 256 * 1024, "prior T2 response size")
        reply = budget.read(prior_response, self.t2_hash)
        split.validated_counts(reply, 435, 122)
        self.first_id = reply["tokens"][0]
        self.prompts = split.Probe(history).prompts
        require(
            [len(x) for x in self.prompts] == [123, 435]
            and split.digest(self.prompts[1]) == prior["after_ready"]["official_vector_sha256"],
            "official IDs",
        )

    def run(self, pid, raw, cancelled, progress):
        deadline = time.monotonic() + self.timeout_s
        port = budget.listener_port(raw)
        first = primer(
            pid, raw, cancelled, progress, self.prompts[0], port, deadline, self.primer_hash
        )
        data, elapsed, sha = budget.exchange(
            pid, raw, cancelled, progress, self.prompts[1], "T2", port, deadline
        )
        observed, _, steps = budget.trajectory(data, elapsed, 435, 122)
        actual = first_emitted(data)
        if actual is not None:
            require(actual == self.first_id, "stock T2 first ID differs from authenticated split")
        if steps:
            require(actual is not None, "missing first T2 ID")
            observed.update(project(observed, steps, first["client_s"]))
        return {
            "protocol_sha256": PROTO,
            "split_receipt_sha256": SPLIT_SHA,
            "first_turn_receipt_sha256": T1_SHA,
            "prior_T2_response_sha256": self.t2_hash,
            "first_T2_id_matches_split": True if actual is not None else None,
            "primer": first,
            "official_T2_ids_sha256": split.digest(self.prompts[1]),
            "T2_request_sha256": sha,
            "T2_sse_sha256": hashlib.sha256(data).hexdigest(),
            **observed,
        }


def main():
    ap = argparse.ArgumentParser(add_help=False, description=__doc__)
    ap.add_argument("--historical-results", type=Path, required=True)
    ap.add_argument("--prior-second-response", type=Path, required=True)
    sys.path.insert(0, str(QUAL / "aster_full_ready"))
    from loader import cli_for

    if "--help" in sys.argv or "-h" in sys.argv:
        ap.print_help()
        cli_for()
        return
    a, rest = ap.parse_known_args()
    sys.argv[1:] = rest
    cli_for(probe=Probe(a.historical_results, a.prior_second_response))


if __name__ == "__main__":
    main()
