"""A generated history followed by the original C131 run-length coding task."""

import hashlib
import json
import time
from itertools import pairwise
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CODE = ROOT / "results/c273-layer-utility-ac-restored-20261004/official-inputs.json"
TASK = "development-code-rle"
GRADER = "c131-code-01"
T1_INPUT = "2d962b19909b8f47f43852fd0ab10255e6052f43b5f527d6f0f1c1b573f422ad"
T1_OUTPUT = "202698125db628161029f02774d9bf781614a9f551d2234cc07fa0a426f7c502"
CODE_SHA = "b46f577699dca09a259a74ded548251f45ce59c78458d7ffc2c7ed3b956b699e"


def need(condition, message):
    if not condition:
        raise ValueError(message)


def image_hash(obj):
    return hashlib.sha256((json.dumps(obj, indent=2, allow_nan=False) + "\n").encode()).hexdigest()


class CodeChat:
    name = "C281_T1_C273_NATURAL_CODE"
    cache_counts = [(0, 2043), (2044, 61)]

    def __init__(self, first_path, sha, grader, ids_hash):
        need(sha(CODE) == CODE_SHA and sha(first_path) == T1_INPUT, "code and nominal inputs")
        old = json.loads(CODE.read_bytes())[TASK]
        first = json.loads(first_path.read_bytes())
        task = old["task"]
        self.grader = grader
        self.messages = task["messages"]
        self.caps = (256, task["cap"])
        need(
            first["messages"] == self.messages[:1]
            and old["reasoning_effort"] == first["template_kwargs"]["reasoning_effort"] == "medium"
            and task["grader"] == GRADER
            and self.caps == (256, 768)
            and task["deadline_s"] == 360,
            "frozen task",
        )
        old_system, body = old["rendered_prompt"].split("<|end|>", 1)
        system = first["rendered_prompt"].split("<|end|>", 1)[0]
        date = first["template_kwargs"]["tesy_template_date"]
        need(
            old_system.count(old["template_date"]) == 1
            and old_system.replace(old["template_date"], date) == system,
            "system template",
        )
        end = 200007
        original, current = old["ids"], first["official_ids"]
        self.ids = [current, current[: current.index(end)] + original[original.index(end) :]]
        second = dict(
            messages=self.messages,
            template_kwargs=first["template_kwargs"],
            rendered_prompt=system + "<|end|>" + body,
            official_ids=self.ids[1],
        )
        self.digests = [image_hash(v) for v in (first, second)]
        self.token_hashes = [ids_hash(v) for v in self.ids]
        need(
            self.digests[0] == T1_INPUT and [len(v) for v in self.ids] == [2043, 2105],
            "input geometry",
        )

    def run(self, out, client, preset, own):
        raw = out / "raw"
        launch = raw / (preset["run_id"] + ".launch.json")
        endpoint = "http://127.0.0.1:" + str(preset["port"])
        until = time.monotonic() + 245
        while not launch.is_file():
            need(
                time.monotonic() < until and not (out / "serve-receipt.json").exists(),
                "inventory or launch failed",
            )
            time.sleep(0.05)
        started = (
            json.loads(launch.read_bytes())["start_inventory"]["popen_invoked_monotonic_ns"] / 1e9
        )
        while True:
            own()
            need(time.monotonic() < started + 180, "readiness deadline")
            try:
                if client.fetch("/health", timeout=1, base_url=endpoint).get("status") == "ok":
                    break
            except (OSError, ValueError, RuntimeError):
                pass
            time.sleep(0.2)
        ready = time.monotonic()
        model = client.fetch("/v1/models", base_url=endpoint)["data"][0]["id"]
        turns = []
        messages = self.messages[:1]
        for index, cap in enumerate(self.caps):
            if index:
                messages = client.assistant_history_messages(
                    messages, turns[0]["message"], self.messages[-1:]
                )
            need(messages == self.messages[: len(messages)], "generated assistant history")
            client.persistent_mappings(own(), preset)
            kwargs = dict(reasoning_effort="medium", tesy_template_date=preset["session_date"])
            req = dict(model=model, messages=messages, chat_template_kwargs=kwargs)
            rendered = client.fetch("/apply-template", req, base_url=endpoint)["prompt"]
            ids = client.fetch(
                "/tokenize",
                dict(content=rendered, add_special=False, parse_special=True),
                base_url=endpoint,
            )["tokens"]
            need(ids == self.ids[index] and len(ids) + cap <= 8192, "full official tokenization")
            label = f"T{index + 1}"
            client.save(
                raw / (label + "-input.json"),
                dict(
                    messages=messages,
                    template_kwargs=kwargs,
                    rendered_prompt=rendered,
                    official_ids=ids,
                ),
            )
            req.update(
                max_tokens=cap,
                temperature=0,
                seed=42,
                stream=True,
                stream_options={"include_usage": True},
                cache_prompt=True,
                return_tokens=True,
                verbose=True,
            )
            start = time.monotonic()
            task = "code-history-first" if not index else TASK
            deadline = 360 if index else 180
            evidence = client.Evidence(raw / (label + "-request.jsonl"), task, start, deadline)
            client._REQUEST_LOCAL.evidence = evidence
            watchdog = client.Deadline(start + deadline, lambda: client.launcher.stop(out))
            watchdog.start()
            try:
                response, metrics = client.stream_chat(req, deadline, start, base_url=endpoint)
                end = time.monotonic()
                choice = response["choices"][0]
                item = dict(
                    id=task,
                    official_ids=ids,
                    response=response,
                    stream_metrics=metrics,
                    request_started_monotonic=start,
                    request_ended_monotonic=end,
                    request_wall_s=end - start,
                    finish_reason=choice["finish_reason"],
                    message=choice["message"],
                    timings=response["timings"],
                    usage=response["usage"],
                    accepted=False,
                )
                client.save(raw / (label + "-complete-unvalidated.json"), item)
                evidence.write("RESPONSE_COMPLETE", completed_monotonic=end, accepted=False)
                need(watchdog.complete(end), "transport deadline")
                client.natural_completion(item, cap, True)
                cached, evaluated = self.cache_counts[index]
                observed = item["timings"]
                need(
                    (observed["cache_n"], observed["prompt_n"]) == (cached, evaluated)
                    and item["usage"]["prompt_tokens"] == len(ids)
                    and item["usage"]["completion_tokens"] == observed["predicted_n"],
                    "cache, work or output denominator",
                )
                if index:
                    client.validate_generated_prefix_cache(
                        self.ids[0],
                        ids,
                        cached,
                        evaluated,
                        turns[0]["usage"]["completion_tokens"],
                        1900,
                        32,
                    )
                    grade = self.grader.grade(GRADER, item["message"]["content"])
                else:
                    grade = dict(
                        status="PASS"
                        if client.grade(0, item["message"]["content"], None)
                        and item["message"]["content"] == self.messages[1]["content"]
                        else "FAIL"
                    )
                client.save(raw / (label + "-functional.json"), grade)
                need(grade["status"] == "PASS", "frozen content validator " + grade["status"])
                need(time.monotonic() < start + deadline, "validation deadline")
                item.update(
                    accepted=True,
                    content_gate="PASS",
                    prefix_gate="PASS",
                    output_ids_authority="NATIVE_TARGET_STDERR",
                )
                evidence.write("REQUEST_TERMINAL", accepted=True, watchdog=watchdog.finish())
                client.save(raw / (label + "-result.json"), item)
                turns.append(item)
            except Exception as exc:
                if not evidence.truncated:
                    evidence.write("REQUEST_TERMINAL", accepted=False, reason=str(exc))
                raise
            finally:
                watchdog.finish()
                evidence.close()
                client._REQUEST_LOCAL.evidence = None
        result = dict(
            status="CLIENT_TWO_REQUESTS_PASS", rows=turns, readiness_after_popen_s=ready - started
        )
        client.save(out / "client-receipt.json", result)
        return result


def serial(log, turn, count, prompt, cap, native):
    events = list(native["events"](log))
    owners = [task for _, task, e in events if e == ("start",)]
    need(len(owners) == len(set(owners)) and turn <= len(owners) <= 2, "native task starts")
    track = [(clock, e) for clock, task, e in events if task == owners[turn - 1]]
    need(all(a[0] <= b[0] for a, b in pairwise(track)), "nonmonotonic native task")
    data = [e for _, e in track]
    ids = [e[3] for e in data if e[0] == "sample"]
    need(len(ids) == count and 0 < count <= cap and ids[-1] == 200002, "EOG or sample count")
    expected = [("start",)]
    for n, token in enumerate(ids, 1):
        if n == count:
            expected.append(("eos",))
        expected.append(("sample", n, cap - n, token))
        if n < count:
            expected.append(("feed", token, prompt + n - 1))
    expected.append(("end", prompt + count - 1))
    need([e[:4] if e[0] == "sample" else e for e in data] == expected, "native sample/feed order")
    digest = native["digest"](native["ids_bytes"](ids))
    if turn == 1:
        need(count == 78 and digest == T1_OUTPUT, "independent C281 turn")
    return dict(
        sampled=count,
        sampled_sha256=digest,
        serial=count - 1,
        proposed=0,
        accepted=0,
        blocks=0,
        eos=1,
    )
