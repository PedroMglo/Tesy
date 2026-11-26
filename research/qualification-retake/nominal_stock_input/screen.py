"""Authenticate both C281 inputs in linked C269/stock Harmony and vocab-only clients."""

import argparse
import hashlib
import json
import os
import re
import signal
import struct
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
AUTHORITIES = {
    "r0": (
        "nvme_conversation/evidence-20261124-r1/evidence.json",
        "f64067231b0936d82ce822ca782adfdb00bb9134b60d46fdc6a5bac3e6d64f74",
    ),
    "render": (
        "aster_template/attempt-01/receipt.json",
        "b906de70d9d2f4f2eebc3187844d03064f16a3c15d3ca6721448cfbec47a90d4",
    ),
    "vocab": (
        "aster_vocab/attempt-03/receipt.json",
        "426579a4b59f356ecb3837764b7d1aa808e90d6c752c19c510ff1164b93d929e",
    ),
}
OFFICIAL = [
    (2043, "0946e5070c4bfcc945d584e0778e33fb544a46bc313201bfc26a5f72f547f7a0"),
    (2197, "cf7e9b19362c5aeaf5e54e2185048acac09ec55459fb4a6fc262ec434f037425"),
]
DAY = "2026-10-05"
CONTROL_DATE = "2000-01-02"
PROCESS_ENV = {
    "PATH": "/usr/bin:/bin",
    "LC_ALL": "C",
    "CUDA_VISIBLE_DEVICES": "",
    "NVIDIA_VISIBLE_DEVICES": "none",
}


def check(ok, label):
    if not ok:
        raise ValueError(label)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pinned(path, digest, size=None, ceiling=32 * 1024**2):
    n = path.stat().st_size
    check(0 < n <= ceiling and (size is None or n == size), "input_size")
    data = path.read_bytes()
    check(len(data) == n and sha(data) == digest, "input_digest")
    return data


def packed_ids(ids):
    check(
        isinstance(ids, list)
        and len(ids) <= 8192
        and all(type(i) is int and 0 <= i < 201088 for i in ids),
        "invalid_ids",
    )
    return struct.pack(f"<{len(ids)}i", *ids)


def frame(data):
    return struct.pack("<I", len(data)) + data


def fields(data):
    values = []
    while data:
        check(len(data) >= 4, "truncated_frame")
        size = struct.unpack_from("<I", data)[0]
        check(0 < size <= len(data) - 4, "invalid_frame")
        values.append(data[4 : 4 + size])
        data = data[4 + size :]
    return values


class Mismatch(Exception):
    def __init__(self, phase, expected, observed, unit):
        i = next(
            (i for i, (a, b) in enumerate(zip(expected, observed, strict=False)) if a != b),
            min(len(expected), len(observed)),
        )
        self.detail = {
            "phase": phase,
            "unit": unit,
            "first_difference_zero_based": i,
            "expected_count": len(expected),
            "observed_count": len(observed),
            "expected_sha256": sha(expected if unit == "byte" else packed_ids(expected)),
            "observed_sha256": sha(observed if unit == "byte" else packed_ids(observed)),
        }
        super().__init__(phase)


def same(phase, expected, observed, unit="byte"):
    if expected != observed:
        raise Mismatch(phase, expected, observed, unit)


def run_child(argv, data):
    proc = subprocess.run(argv, input=data, capture_output=True, env=PROCESS_ENV, timeout=20)
    check(
        proc.returncode == 0 and len(proc.stdout) < 256 * 1024 and len(proc.stderr) < 512 * 1024,
        "native_client",
    )
    return proc.stdout


def linked(exe, expected):
    report = run_child(["/usr/bin/ldd", exe], b"").decode()
    check("not found" not in report, "unresolved_lib")
    identities = {}
    for name, desired in expected.items():
        lines = re.findall(
            r"^\s*" + re.escape(name) + r"(?:\.[0-9]+)*\s+=>\s+(\S+)\s+\(", report, re.M
        )
        check(len(lines) == 1, "linked_object_cardinality")
        p = Path(lines[0]).resolve(strict=True)
        pinned(p, desired, ceiling=128 * 1024**2)
        identities[name] = desired
    return identities


def messages_bytes(messages):
    return b"".join(frame(m[k].encode()) for m in messages for k in ("role", "content"))


def git(*args):
    return subprocess.check_output(
        [
            "git",
            "--no-optional-locks",
            "-c",
            "core.preloadIndex=false",
            "-c",
            "index.threads=1",
            "-C",
            str(HERE),
            *args,
        ],
        text=True,
    ).strip()


def screen(a, r):
    check(not git("status", "--porcelain"), "dirty_tree")
    r.update(
        measurement_commit=git("rev-parse", "HEAD"),
        measurement_tree=git("rev-parse", "HEAD^{tree}"),
        program_sha256=sha(Path(__file__).read_bytes()),
        protocol_sha256=sha((HERE / "protocol.md").read_bytes()),
    )
    auth = {k: json.loads(pinned(BASE / file, h)) for k, (file, h) in AUTHORITIES.items()}
    evidence, render, vocab = (auth[x] for x in ("r0", "render", "vocab"))
    check(
        evidence["status"] == "PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY"
        and evidence["session_date"] == DAY
        and [x["functional"] for x in evidence["rows"]] == ["PASS", "PASS"],
        "prior_conversation",
    )
    manifest = evidence["local_manifest"]

    def original(name):
        meta = manifest["raw/" + name]
        return json.loads(pinned(a.session_raw / name, meta["sha256"], meta["bytes"]))

    original_template = pinned(a.original_jinja, render["original_template_sha256"])
    binding = b'strftime_now("%Y-%m-%d")'
    dated = pinned(a.render_bin / "fixed.jinja", render["adapted_template_sha256"])
    check(
        original_template.count(binding) == 1
        and original_template.replace(binding, b"tesy_template_date") == dated,
        "one_date_binding",
    )
    official_vocab = a.vocab_bin / "vocab.gguf"
    pinned(official_vocab, vocab["vocab_copy_sha256"], vocab["vocab_copy_bytes"])
    check(vocab["vocab_copy_bytes"] == 12980384 and vocab["copied_tensors"] == 0, "vocab_only")
    r.update(
        original_jinja_sha256=sha(original_template),
        stock_jinja_sha256=sha(dated),
        vocab_copy_sha256=vocab["vocab_copy_sha256"],
        template_date=DAY,
        sources={k: h for k, (_, h) in AUTHORITIES.items()},
        binaries={},
        dependencies={},
        turns=[],
    )
    for engine in ("C269", "stock"):
        renderer = a.render_bin / engine
        tokenizer = a.vocab_bin / engine
        render_sha = render["compilations"][engine]["binary_sha256"]
        tok_sha = vocab["executables_sha256"][engine]
        pinned(renderer, render_sha)
        pinned(tokenizer, tok_sha)
        r["binaries"][engine] = {"renderer": render_sha, "tokenizer": tok_sha}
        deps = vocab["libraries_sha256"][engine]
        r["dependencies"][engine] = {
            "renderer": linked(
                renderer,
                dict(deps, **{"libllama-common.so": render["linked_common_sha256"][engine]}),
            ),
            "tokenizer": linked(tokenizer, deps),
        }
    previous = None
    prior_ids = []
    for index, (n, ids_sha) in enumerate(OFFICIAL, 1):
        r["phase"] = f"T{index}_input"
        raw = original(f"T{index}-input.json")
        payload = raw["messages"]
        history = raw["official_ids"]
        check(sha(packed_ids(history)) == ids_sha and len(history) == n, "historical_ids")
        check(
            raw["template_kwargs"] == {"reasoning_effort": "medium", "tesy_template_date": DAY}
            and [m["role"] for m in payload]
            == (["user"] if index == 1 else ["user", "assistant", "user"])
            and all(
                set(m) == {"role", "content"} and isinstance(m["content"], str) for m in payload
            ),
            "message_contract",
        )
        if index == 2:
            first = original("T1-result.json")
            check(
                first["id"] == "c112-code"
                and first["accepted"] is True
                and first["content_gate"] == "PASS"
                and first["finish_reason"] == "stop"
                and first["message"]["role"] == "assistant"
                and payload[:-1]
                == previous + [{"role": "assistant", "content": first["message"]["content"]}],
                "natural_history",
            )
        expected = raw["rendered_prompt"].encode()
        current = ("Current date: " + DAY + "\n").encode()
        other = ("Current date: " + CONTROL_DATE + "\n").encode()
        check(expected.count(current) == 1 and other not in expected, "system_date")
        turn = {
            "index": index,
            "historical_input_sha256": manifest[f"raw/T{index}-input.json"]["sha256"],
            "historical_render_bytes": len(expected),
            "expected_render_sha256": sha(expected),
            "expected_id_count": n,
            "expected_ids_i32le_sha256": ids_sha,
            "engines": {},
        }
        r["turns"].append(turn)
        enc = messages_bytes(payload)
        for engine in ("C269", "stock"):
            renderer = a.render_bin / engine
            tmpl = a.original_jinja if engine == "C269" else a.render_bin / "fixed.jinja"
            row = turn["engines"][engine] = {}
            r["phase"] = f"T{index}_{engine}_render"
            result = run_child([renderer, tmpl, DAY], enc)
            same(r["phase"], expected, result)
            row["render_sha256"] = sha(result)
            r["phase"] = f"T{index}_{engine}_negative_date"
            neg = run_child([renderer, tmpl, CONTROL_DATE], enc)
            same(r["phase"], expected.replace(current, other, 1), neg)
            row["date_control_sha256"] = sha(neg)
            r["phase"] = f"T{index}_{engine}_tokenizer"
            outputs = fields(
                run_child([a.vocab_bin / engine, "--tokenize", official_vocab], frame(result))
            )
            check(
                len(outputs) == 2
                and sha(outputs[0]) == sha(original_template)
                and len(outputs[1]) % 4 == 0,
                "embedded_template_or_token_frame",
            )
            observed = list(struct.unpack(f"<{len(outputs[1]) // 4}i", outputs[1]))
            same(r["phase"], history, observed, "id")
            row.update(
                official_ids_match=True, ids_i32le_sha256=sha(outputs[1]), id_count=len(observed)
            )
        turn["status"] = "PASS_RENDER_AND_OFFICIAL_IDS"
        if prior_ids:
            r["prompt_ids_common_prefix"] = next(
                (k for k, (x, y) in enumerate(zip(prior_ids, history, strict=False)) if x != y),
                min(len(prior_ids), len(history)),
            )
        previous, prior_ids = payload, history
    r.update(status="PASS_TWO_NOMINAL_INPUTS_RENDER_AND_OFFICIAL_IDS", phase="complete")


def expired(signum, frame):
    raise TimeoutError("unit_timeout")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for opt in ("session-raw", "render-bin", "vocab-bin", "original-jinja", "new-output-dir"):
        parser.add_argument("--" + opt, type=Path, required=True)
    a = parser.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700, exist_ok=False)
    r = {
        "cache_observed": "NOT_RUN",
        "stock_product": "NOT_RUN",
        "model_forwards": 0,
        "gpu_used": False,
        "full_gguf_opened": False,
        "phase": "setup",
    }
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(180)
    try:
        screen(a, r)
    except FileNotFoundError as e:
        r.update(status="NOT_RUN_REQUIRED_INPUT", reason=Path(e.filename).name)
    except Mismatch as e:
        r.update(status="FAIL_FIRST_DIFFERENCE", difference=e.detail)
    except Exception as e:
        r.update(status="FAIL", reason=f"{type(e).__name__}: {e}")
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(r, f, indent=2, sort_keys=True)
        f.write("\n")
    print(r["status"], r["phase"])
    return int(not r["status"].startswith("PASS_"))


if __name__ == "__main__":
    raise SystemExit(main())
