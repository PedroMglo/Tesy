"""Find observational witnesses for the natural turn, with the original chat serializer."""

import argparse
import hashlib
import importlib.util
import itertools
import json
import math
import os
import signal
import subprocess
from pathlib import Path

PROTOCOL = "82c617a253e88756b743f1c839ef60ae2b0222a4c795767a689e82487ec72f23"
NATURAL = "f64067231b0936d82ce822ca782adfdb00bb9134b60d46fdc6a5bac3e6d64f74"
VOCAB_RECEIPT = "426579a4b59f356ecb3837764b7d1aa808e90d6c752c19c510ff1164b93d929e"
VOCAB = "ac4566b560fe2df4e0f4f9eb071ce8803af7107c022b4a643a842560ba8b7049"
PIECES = "bebcd35855773428a422d187dec1bc65e97b2e1d452b800232059897064a2bd3"
RULE = "797746256c463790abc44463e56948636fa63b03f9d0e710daa29203f8a9846e"
ARMS = ("final", "commentary")


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def checked(path, digest, size=None):
    if size is not None:
        require(path.stat().st_size == size, "file size")
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == digest, "file digest")
    return data


def module(path, name, digest):
    checked(path, digest)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_natural(base, raw):
    manifest = base / "nvme_conversation/evidence-20261124-r1/evidence.json"
    cert = json.loads(checked(manifest, NATURAL))
    def sealed(name):
        mark = cert["local_manifest"]["raw/" + name]
        return checked(raw / name, mark["sha256"], mark["bytes"])
    prompt = json.loads(sealed("T2-input.json"))["official_ids"]
    result = json.loads(sealed("T2-result.json"))
    require(prompt == result["official_ids"] and len(prompt) == 2197, "official prompt")
    require(result["output_ids"] is None and result["usage"] == {
        "completion_tokens": 47, "prompt_tokens": 2197, "total_tokens": 2244,
        "prompt_tokens_details": {"cached_tokens": 2044}},
            "completion identity")
    rows = (json.loads(s) for s in sealed("T2-request.jsonl").splitlines())
    fragments = [r["fragment"].strip() for r in rows if r["kind"] == "SSE_FRAGMENT"]
    frames = [json.loads(s[6:]) for s in fragments
              if s.startswith("data: ") and s != "data: [DONE]"]
    require(len(fragments) == 81 and len(frames) == 40 and fragments.count("data: [DONE]") == 1,
            "stream frame count")
    reasoning, final, kinds = [], [], []
    for frame in frames:
        choices = frame["choices"]
        if not choices:
            require(frame["usage"] == result["usage"], "terminal usage")
            kinds.append("usage")
            continue
        require(len(choices) == 1 and not choices[0].get("logprobs"), "choice")
        choice = choices[0]
        delta = choice["delta"]
        if delta == {"role": "assistant", "content": None}:
            kinds.append("role")
        elif choice.get("finish_reason") == "stop" and not delta:
            kinds.append("stop")
        elif set(delta) == {"reasoning_content"} and delta["reasoning_content"]:
            reasoning.append(delta["reasoning_content"])
            kinds.append("reasoning")
        elif set(delta) == {"content"} and delta["content"]:
            final.append(delta["content"])
            kinds.append("final")
        else:
            raise ValueError("unqualified chat event")
    require(kinds == ["role"] + 35 * ["reasoning"] + 2 * ["final"] + ["stop", "usage"],
            "chat event order")
    require(all(s.isascii() for s in [*reasoning, *final])
            and sum(map(len, reasoning)) == 162 and sum(map(len, final)) == 5, "visible channels")
    verbose, = [x["__verbose"] for x in frames if "__verbose" in x]
    g = verbose["generation_settings"]
    require(verbose["tokens"] == [] and verbose["stop_type"] == "eos"
            and g["generation_prompt"] == "<|start|>assistant" and g["chat_format"] == "peg-native"
            and g["reasoning_format"] == "deepseek" and g["ignore_eos"] is False and not g["stop"]
            and not g["grammar"] and g["n_probs"] == 0 and not g["logit_bias"]
            and len(g["preserved_tokens"]) == 5, "generation settings")
    return prompt, reasoning, final


def cases(pieces, reasoning, final, channel):
    # Restricted construction; native to_json() independently verifies each selected sequence.
    texts = ["<|channel|>", "analysis", "<|message|>", *reasoning, "<|end|>",
             "<|start|>", "assistant", "<|channel|>", channel, "<|message|>", *final, "<|return|>"]
    wanted = {s.encode() for s in texts}
    reverse = {s: [] for s in wanted}
    for idx, (kind, piece) in pieces.items():
        if piece in reverse and (kind == 1 or kind in (3, 4) and piece.startswith(b"<|")):
            reverse[piece].append(idx)
    axes = [reverse[s.encode()] for s in texts]
    require(len(axes) == 47, "witness width")
    require(math.prod(map(len, axes)) <= 64, "witness enumeration cap")
    return itertools.product(*axes)


def main(args):
    base = args.repo / "research/qualification-retake"
    checked(Path(__file__).with_name("protocol.md"), PROTOCOL)
    checked(args.witness, args.witness_sha256)
    cert = json.loads(checked(base / "aster_vocab/attempt-03/receipt.json", VOCAB_RECEIPT))
    require(cert["vocab_copy_sha256"] == VOCAB and cert["vocab_copy_bytes"] == 12980384,
            "vocabulary metadata")
    prompt, reasoning, final = read_natural(base, args.natural_root / "raw")
    lookup = module(base / "aster_reasoning_prefix/screen.py", "natural_pieces", PIECES).lookup
    replay = module(base / "history_lookup/causal_pair/screen.py", "natural_ngram", RULE).replay
    pieces = lookup(checked(args.vocab_only, VOCAB, 12980384), set(range(201088)))
    arms = {}
    for channel in ARMS:
        attempted = []
        for ids in cases(pieces, reasoning, final, channel):
            msg = {"ids": ids, "reasoning_deltas": reasoning, "final_deltas": final}
            proc = subprocess.run([str(args.witness.resolve()), str(args.vocab_only.resolve())],
                                  input=json.dumps(msg).encode(), capture_output=True, timeout=30)
            require(proc.returncode == 0, "native verifier exited before evidence")
            report = json.loads(proc.stdout)
            status = report["status"]
            ends = report["eog_ids"]
            require(isinstance(ends, list) and len(ends) == len(set(ends)), "EOG list")
            if status == "REJECT_PROJECTED_STREAM":
                require(not ends, "mismatch disposition")
                attempted.append({"status": status, "variants": 0})
                continue
            require(status == "PASS_REAL_C269_PEG_WITNESS" and ends
                    and report["sample_count"] == 47 and report["reasoning_deltas"] == 35
                    and report["final_deltas"] == 2 and report["chat_events"] == 40
                    and report["vocab_size"] == 201088, "native verification")
            require(all(type(e) is int and 0 <= e < 201088 for e in ends), "EOG range")
            require(report["eog_tested"] >= len(ends), "EOG population")
            unique = {}
            for e in ends:
                target = (*ids[:-1], e)
                outcomes = {}
                for length in (32, 46):
                    stats = replay(prompt, target[:length + 1], 2, 2)
                    n_b = stats["proposals"]
                    stats["max_B3_over_AR_for_15pct"] = (
                        (0.85 * length - stats["ordinary"]) / n_b if n_b else None)
                    outcomes[str(length)] = stats
                key = json.dumps(outcomes, sort_keys=True)
                unique[key] = unique.get(key, 0) + 1
            attempted.append({"status": status, "variants": len(ends),
                              "eog_tested": report["eog_tested"], "distinct_work": [
                {"multiplicity": count, "windows": json.loads(key)} for key, count in unique.items()
            ]})
        arms[channel] = attempted
    witnessed = sum(a["variants"] for rows in arms.values() for a in rows)
    require(witnessed >= 2, "two distinct verified sequences required")
    return dict(
        status="NON_UNIQUE_OBSERVATIONALLY_COMPATIBLE",
        coverage="CONSTRUCTIVE_WITNESSES_ONLY", economic_verdict="INCONCLUSIVE",
        schema="natural47-witness-v1", event_objects=40, completion_ids=47,
        witnessed=witnessed, channels=arms, native_executable_sha256=args.witness_sha256,
        program_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        protocol_sha256=PROTOCOL, target_vocabulary_sha256=VOCAB, model_forwards=0, gpu_used=False,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for name in ("repo", "natural-root", "vocab-only", "witness", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--witness-sha256", required=True)
    args = p.parse_args()
    signal.alarm(120)
    args.new_output_dir.mkdir(mode=0o700, exist_ok=False)
    try:
        receipt = main(args)
    except (ValueError, KeyError, TimeoutError, OSError, subprocess.SubprocessError) as exc:
        receipt = {"status": "INCONCLUSIVE_PRESERVED", "error_class": type(exc).__name__,
                   "reason": str(exc) if type(exc) is ValueError
                   else "input or native verifier"}
    data = json.dumps(receipt, sort_keys=True, allow_nan=False, indent=2) + "\n"
    require(len(data.encode()) < 1 << 20, "receipt cap")
    pending = args.new_output_dir / ".pending"
    pending.write_text(data)
    os.rename(pending, args.new_output_dir / "receipt.json")
    raise SystemExit(int(receipt["status"] != "NON_UNIQUE_OBSERVATIONALLY_COMPATIBLE"))
