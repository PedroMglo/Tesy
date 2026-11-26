"""One independent, natural stock chat response on the authenticated fixed C133 T2 history."""

import hashlib
import math
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(QUAL), str(ROOT / "tools")]

import optin_integration_client as original  # noqa: E402
import two_turn_pair as pair  # noqa: E402
from aster_budget.probe import listener_port  # noqa: E402
from aster_split import probe as split  # noqa: E402
from aster_turn2_budget.probe import SPLIT_SHA, primer  # noqa: E402
from c2_gate import strict_json  # noqa: E402
from c2_server_run import _REQUEST_LOCAL  # noqa: E402
from request_evidence import Evidence  # noqa: E402

PRODUCT_SECONDS = 600
INPUT = "0a96782a6be10028f4d91bbbd5d0f1efafe7327e6364281645fe0e7db5795b9f"
T2 = "acdc1fc68a6fefcd7a30c6a9637b44d3187d1ce97f58d582fcf6fdc5379170ea"
PRIMER = "9b0b6b2b9553b98347f75303d20c656f39c2f124e4935a127ae1c93401252e07"
COST_SHA = "75d34fe5420d78176f9ea7269c41dca1224108cb6ff7072cf59442988b39b209"
RENDER_SHA = "b906de70d9d2f4f2eebc3187844d03064f16a3c15d3ca6721448cfbec47a90d4"
RENDER = "76ae0367d000c88fa3e4862575e464feda62e8a37be2e115c33cf9916ce14763"
GRADE = "4678d8c4f2db5da95acc70be985378079824ab788ef808328f736aa54d1dbf6f"
RETRY = "97a1202e1a14088fd050d41e40b085f66cd251dba7b43ab2ed75cb9c8e3e6469"


class Gate(ValueError):
    pass


def check(ok, label):
    if not ok:
        raise Gate(label)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check_ids(observed, expected):
    check(
        isinstance(observed, list)
        and len(observed) == len(expected)
        and all(type(v) is int and 0 <= v < 201088 for v in observed)
        and observed == expected,
        "T2_official_ID_mismatch",
    )


def comparison(content_pass, matches_literal, transport_s, validated_s):
    check(
        all(type(v) in (float, int) and math.isfinite(v) for v in (transport_s, validated_s))
        and 0 <= transport_s <= validated_s,
        "validation_clocks",
    )
    return {
        "stock_T2_C132_grade": "PASS" if content_pass else "FAIL",
        "Aster_in_final_casefold": matches_literal,
        "historical_R0_T2_C132_grade": "FAIL",
        "historical_R0_Aster_in_final_casefold": False,
        "content_contrast": (
            "OBSERVED_DIFFERENCE_ON_FIXED_HISTORY"
            if content_pass
            else "BOTH_OMIT_ASTER_ON_FIXED_HISTORY"
        ),
        "transport_within_600s": transport_s < PRODUCT_SECONDS,
        "validated_within_600s": validated_s < PRODUCT_SECONDS,
        "C133_clock_observation": "COMPLETE_WITHIN_BUDGET"
        if validated_s < PRODUCT_SECONDS
        else "CENSORED_AT_600S_DIAGNOSTIC_CONTINUATION",
        "causal_attribution": "INCONCLUSIVE",
        "natural_two_turn_session": "NOT_RUN",
    }


class Journal(Evidence):
    def __init__(self, path, start, deadline, state, cancelled):
        self.state = state
        self.cancelled = cancelled
        super().__init__(path, "c133-turn02", start, deadline - start)

    def write(self, kind, **data):
        super().write(kind, **data)
        if kind != "SSE_FRAGMENT":
            return
        now = time.monotonic()
        check(now < self.deadline and not self.cancelled.is_set(), "diagnostic_deadline_or_cancel")
        line = data["fragment"].strip()
        if line.startswith("data: ") and line[6:] != "[DONE]":
            obj = strict_json(line[6:])
            for choice in obj["choices"]:
                delta = choice["delta"]
                for src, dest in (
                    ("content", "first_final_s"),
                    ("reasoning_content", "first_reasoning_s"),
                ):
                    text = delta.get(src)
                    if isinstance(text, str) and text.strip() and self.state.get(dest) is None:
                        self.state[dest] = now - self.started


class Probe:
    run_id = "stock-aster-fixed-natural-reference"
    ram_profile = "E10"
    pass_status = "PASS_FIXED_ASTER_NATURAL_ENVELOPE"
    protocol_path = HERE / "protocol.md"
    timeout_s = 3000

    def __init__(self, history):
        check(
            sha(Path(pair.session.__file__).read_bytes()) == GRADE
            and sha(Path(pair.historical.__file__).read_bytes()) == RETRY,
            "frozen_C133_tools",
        )
        manifest, specs, _, self.messages = pair.prepare(history)
        self.spec = specs[1]
        self.turn_authority = manifest["turns"][1]
        self.primer_ids, self.official = split.Probe(history).prompts
        check(
            pair.digest(manifest) == INPUT
            and pair.digest(self.official) == T2
            and self.turn_authority["messages_sha256"] == pair.digest(self.messages)
            and self.spec.get("required") == ["Aster"]
            and not self.spec.get("required_any"),
            "historical_content_authority",
        )
        split_rec = pair.read(QUAL / "aster_split/physical-r1/receipt.json", SPLIT_SHA)
        cost = pair.read(QUAL / "aster_turn2_budget/physical-r1/receipt.json", COST_SHA)
        render = pair.read(QUAL / "aster_template/attempt-01/receipt.json", RENDER_SHA)
        check(
            split_rec["after_ready"]["requests"][0]["request_sha256"] == PRIMER
            and cost["after_ready"]["primer"]["request_sha256"] == PRIMER
            and cost["after_ready"]["official_T2_ids_sha256"] == T2
            and cost["after_ready"]["first_T2_id_matches_split"] is True
            and render["turns"][1]["stock_bound_sha256"] == RENDER
            and render["turns"][1]["render_bytes"] == 2029,
            "fixed_input_history",
        )
        self.pins = {
            key: manifest[key]
            for key in (
                "decision_sha256",
                "raw_sha256",
                "receipt_sha256",
                "protocol_sha256",
                "tokenizations_sha256",
                "workload_sha256",
            )
        }
        self.pins.update(
            validators=[GRADE, RETRY],
            input_manifest_sha256=INPUT,
            render_receipt_sha256=RENDER_SHA,
            split_receipt_sha256=SPLIT_SHA,
            fixed_budget_receipt_sha256=COST_SHA,
            primer_request_sha256=PRIMER,
        )

    def run(self, pid, raw, cancelled, progress):
        deadline = time.monotonic() + self.timeout_s
        port = listener_port(raw)
        endpoint = f"http://127.0.0.1:{port}"
        state = {
            "phase": "primer",
            "turn": 2,
            "completed_turns": 0,
            "first_final_s": None,
            "first_reasoning_s": None,
        }
        progress["product_progress"] = state

        def verified():
            check(time.monotonic() < deadline and not cancelled.is_set(), "deadline_or_cancel")
            split.owned_listener(pid, port)

        def fetch(path, payload=None):
            verified()
            return original.fetch(
                path, payload, base_url=endpoint, timeout=min(10, deadline - time.monotonic())
            )

        timer = None
        lock = threading.RLock()
        completed = False

        def censor():
            with lock:
                if completed or state.get("product_cutoff_observed_monotonic_s") is not None:
                    return
                state["product_cutoff_observed_monotonic_s"] = time.monotonic()
                state["product_600s"] = "CENSORED_AT_600S_DIAGNOSTIC_CONTINUATION"
                original.save(
                    raw / "T2-product-censor.json",
                    {
                        "status": state["product_600s"],
                        "deadline_monotonic_s": state["product_deadline_monotonic_s"],
                        "observed_monotonic_s": state["product_cutoff_observed_monotonic_s"],
                        "diagnostic_connection_continues": True,
                    },
                )

        try:
            p = primer(pid, raw, cancelled, progress, self.primer_ids, port, deadline, PRIMER)
            original.save(raw / "primer-validated.json", p)
            state.update(phase="model_id", primer_accepted=True, primer_s=p["client_s"])
            models = fetch("/v1/models")["data"]
            check(
                len(models) == 1 and isinstance(models[0]["id"], str) and models[0]["id"],
                "served_model_identity",
            )
            body = pair.payload(models[0]["id"], self.messages)
            state["phase"] = "render"
            rendered = fetch("/apply-template", body)["prompt"]
            check(
                isinstance(rendered, str) and sha(rendered.encode()) == RENDER, "T2_render_digest"
            )
            state["phase"] = "tokenize"
            for add in (False, True):
                ids = fetch(
                    "/tokenize", {"content": rendered, "add_special": add, "parse_special": True}
                )["tokens"]
                check_ids(ids, self.official)
            original.save(
                raw / "T2-input.json",
                {"request": body, "rendered_prompt": rendered, "official_ids": ids},
            )
            verified()
            start = time.monotonic()
            remaining = deadline - start
            check(remaining > 0, "post_READY_budget")
            state.update(
                phase="chat",
                send_monotonic_s=start,
                deadline_monotonic_s=deadline,
                product_deadline_monotonic_s=start + PRODUCT_SECONDS,
                product_600s="PENDING",
                verified_T2_ids=len(ids),
            )
            journal = Journal(raw / "T2-request.jsonl", start, deadline, state, cancelled)
            timer = threading.Timer(max(0.0, start + PRODUCT_SECONDS - time.monotonic()), censor)
            timer.daemon = True
            timer.start()
            _REQUEST_LOCAL.evidence = journal
            try:
                progress["http_requests_sent"] += 1
                progress["sampling_tokens_requested"] += pair.POLICY["max_tokens"]
                response, metrics = original.stream_chat(body, remaining, start, base_url=endpoint)
                end = time.monotonic()
                original.save(raw / "T2-response.json", response)
                journal.write("TRANSPORT_COMPLETE", complete_monotonic_s=end)
            finally:
                _REQUEST_LOCAL.evidence = None
                journal.close()
            choice = response["choices"][0]
            state["phase"] = "validate"
            row = {
                "id": pair.IDS[1],
                "source_task_id": pair.IDS[1],
                "message": choice["message"],
                "finish_reason": choice["finish_reason"],
                "usage": response["usage"],
                "timings": response["timings"],
                "stream_metrics": metrics,
            }
            counts, grade = pair.check_response(row, self.official, 1, self.spec)
            check(counts == (435, 122, 313), "observed_T2_split")
            literal = "aster" in row["message"]["content"].casefold()
            check(grade == literal, "validator_literal_disagrees")
            t = row["timings"]
            check(
                all(
                    type(t[k]) in (int, float) and math.isfinite(t[k]) and t[k] >= 0
                    for k in ("prompt_ms", "predicted_ms", "predicted_per_second")
                ),
                "server_clocks",
            )
            transport = end - start
            first_final = metrics["first_final_content_chunk_s"]
            check(0 <= first_final <= transport, "SSE_clocks")
            verified()
            with lock:
                validated = time.monotonic() - start
                if validated >= PRODUCT_SECONDS:
                    censor()
                completed = True
            result = comparison(grade, literal, transport, validated)
            state.update(
                phase="complete", completed_turns=1, product_600s=result["C133_clock_observation"]
            )
            return {
                "scope": "ONE_FIXED_HISTORY_T2_DIAGNOSTIC",
                "historical_sources": self.pins,
                "protocol_sha256": sha(self.protocol_path.read_bytes()),
                "primer": p,
                "rendered_utf8_sha256": RENDER,
                "official_ids_sha256": T2,
                "counts": counts,
                "add_special_false_true_match": True,
                "input_messages_sha256": self.turn_authority["messages_sha256"],
                "request_sha256": pair.digest(body),
                "request_hash_format": "canonical_sorted_JSON",
                "completion_n": row["usage"]["completion_tokens"],
                "natural_stop": True,
                "server_prefill_s": t["prompt_ms"] / 1000,
                "server_decode_s": t["predicted_ms"] / 1000,
                "server_decode_tok_s": t["predicted_per_second"],
                "first_final_s": first_final,
                "first_text_s": metrics["first_text_chunk_s"],
                "first_reasoning_s": metrics["first_reasoning_chunk_s"],
                "transport_complete_s": transport,
                "validated_terminal_s": validated,
                "post_ready_client_s": self.timeout_s - (deadline - time.monotonic()),
                **result,
            }
        except Exception as e:
            label = str(e) if isinstance(e, Gate) else type(e).__name__
            if time.monotonic() >= deadline:
                label = "POST_READY_DIAGNOSTIC_TIMEOUT"
            state["failure"] = label
            if state.get("send_monotonic_s") is not None:
                state["elapsed_since_T2_send_s"] = time.monotonic() - state["send_monotonic_s"]
                if state["elapsed_since_T2_send_s"] >= PRODUCT_SECONDS:
                    censor()
            original.save(raw / "fixed-reference-failure.json", state)
            raise Gate(label) from None
        finally:
            if timer is not None:
                timer.cancel()
                timer.join()
