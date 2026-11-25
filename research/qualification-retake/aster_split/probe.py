"""Two fixed-ID requests on an already qualified stock server. No transcript is published."""

import argparse
import hashlib
import http.client
import math
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(HERE.parent), str(HERE.parent / "nvme_conversation")]
from aster_cache_geometry.verify import probe_inputs  # noqa: E402
from c2_gate import strict_json  # noqa: E402
from c2_server_run import digest, json_bytes  # noqa: E402
from contract import owned_listener  # noqa: E402


def require(condition, label):
    if not condition:
        raise ValueError(label)


def validated_counts(data, length, cached):
    timings = data["timings"]
    expected = {
        "id_slot": 0,
        "tokens_predicted": 1,
        "tokens_evaluated": length,
        "cache_n": cached,
        "prompt_n": length - cached,
        "predicted_n": 1,
    }
    observed = {
        k: timings[k] if k in ("cache_n", "prompt_n", "predicted_n") else data[k] for k in expected
    }
    require(all(type(n) is int for n in observed.values()), "noninteger server counts")
    require(data["stop"] is True and data["truncated"] is False, "unfinished or truncated request")
    require(observed == expected, f"server counts {observed} expected {expected}")
    require(
        len(data["tokens"]) == 1
        and type(data["tokens"][0]) is int
        and 0 <= data["tokens"][0] < 201088,
        "missing target token",
    )
    for key in ("prompt_ms", "predicted_ms"):
        require(
            type(timings[key]) in (float, int)
            and math.isfinite(timings[key])
            and timings[key] >= 0,
            "invalid server phase duration",
        )
    return observed | {"prompt_ms": timings["prompt_ms"], "predicted_ms": timings["predicted_ms"]}


def save(path, data):
    with path.open("xb") as stream:
        stream.write(data)


class Probe:
    run_id = "stock-aster-full-fixed-split"
    pass_status = "PASS_STOCK_FULL_SWA_FIXED_122_313"
    timeout_s = 420
    protocol_path = HERE / "protocol.md"

    def __init__(self, history):
        self.prompts = probe_inputs(history)
        require(
            digest(self.prompts[0])
            == "d815d79c3184974e26763dee845e1555cc8a46aa356abe753c81a49432cb9516",
            "primer bytes changed",
        )

    def run(self, pid, raw, cancelled, progress):
        log = (raw / "server.log").read_text(errors="replace")
        ports = set(re.findall(r"listening on http://127\.0\.0\.1:(\d+)\b", log))
        require(len(ports) == 1, "missing unique stock listener")
        port = int(ports.pop())
        record = {
            "protocol_sha256": hashlib.sha256(self.protocol_path.read_bytes()).hexdigest(),
            "official_vector_sha256": digest(self.prompts[1]),
            "requests": [],
        }
        save(raw / "split-inputs.json", json_bytes(record))
        start = time.monotonic()
        for index, (tokens, cache_n) in enumerate(zip(self.prompts, (0, 122), strict=True), 1):
            require(not cancelled.is_set(), "cancelled by monitor")
            owned_listener(pid, port)
            body = json_bytes(
                {
                    "prompt": tokens,
                    "n_predict": 1,
                    "id_slot": 0,
                    "cache_prompt": True,
                    "temperature": 0,
                    "seed": 42,
                    "stream": False,
                    "return_tokens": True,
                }
            )
            save(raw / f"request-{index}.json", body)
            before = time.monotonic()
            connection = http.client.HTTPConnection(
                "127.0.0.1", port, timeout=max(1, self.timeout_s - (before - start))
            )
            try:
                progress["http_requests_sent"] += 1
                progress["sampling_tokens_requested"] = progress["http_requests_sent"]
                connection.request(
                    "POST", "/completion", body, {"Content-Type": "application/json"}
                )
                response = connection.getresponse()
                reply = response.read(256 * 1024 + 1)
                after = time.monotonic()
                save(raw / f"response-{index}.json", reply)
                meta = {
                    "http_status": response.status,
                    "send_monotonic_s": before,
                    "complete_monotonic_s": after,
                    "client_s": after - before,
                    "request_sha256": hashlib.sha256(body).hexdigest(),
                    "response_sha256": hashlib.sha256(reply).hexdigest(),
                }
                save(raw / f"exchange-{index}.json", json_bytes(meta))
                require(response.status == 200 and len(reply) <= 256 * 1024, "HTTP or byte budget")
                counts = validated_counts(strict_json(reply), len(tokens), cache_n)
                record["requests"].append(meta | counts)
            finally:
                connection.close()
        return record


def main():
    parser = argparse.ArgumentParser(add_help=False, description=__doc__)
    parser.add_argument("--historical-results", required=True, type=Path)
    sys.path.insert(0, str(HERE.parent / "aster_full_ready"))
    from loader import cli_for

    if "--help" in sys.argv or "-h" in sys.argv:
        parser.print_help()
        cli_for()
        return
    args, rest = parser.parse_known_args()
    sys.argv[1:] = rest
    cli_for(probe=Probe(args.historical_results))


if __name__ == "__main__":
    main()
