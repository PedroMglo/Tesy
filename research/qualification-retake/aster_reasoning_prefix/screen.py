"""Compare only the unambiguous first partial Harmony channel of an authenticated stream."""

import argparse
import hashlib
import io
import json
import re
import struct
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
SOURCE = {
    "stock": (
        "stock-e95426-sm89-20261124b/source",
        "e95426f16982054c379ca7bdc8186996dd22f0fe",
        {
            "common/parsers/gpt-oss.cpp": "4cbf929f9bfd89e12d7494b400b381d3f0a5f49c",
            "common/chat-peg-parser.cpp": "74b81dcddb27bf38b53728db3938463e574a9e94",
            "common/peg-parser.cpp": "e2ccb77bb14f2d96a8a39722b6f049c601c10e86",
            "common/chat.cpp": "5f956e64e6f300e3ab6faed240b0c9f9e3c0a762",
        },
    ),
    "C75": (
        "streaming",
        "27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5",
        {
            "common/chat.cpp": "544f95763e33a294086a3e668c98cd6e1483ee5f",
            "common/chat-peg-parser.cpp": "a309f02765b7e965d6e3bd6044adf280026749b8",
            "tools/server/server-task.cpp": "775f50bafb224e022c1499ba48743b324a617124",
        },
    ),
}
VOCAB = "ac4566b560fe2df4e0f4f9eb071ce8803af7107c022b4a643a842560ba8b7049"
C133 = "70975912055a8546a9d93f56472e04b95e0e79f066f94d99e5d3a6160406c35b"
RECEIPT = "75d34fe5420d78176f9ea7269c41dca1224108cb6ff7072cf59442988b39b209"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def check(ok):
    if not ok:
        raise ValueError("identity or schema mismatch")


def checked(path, expected):
    data = path.read_bytes()
    check(sha(data) == expected)
    return data


def source_check(backends):

    for path, commit, blobs in SOURCE.values():
        for name, blob in blobs.items():
            data = subprocess.check_output(
                ["git", "-C", str(backends / path), "show", commit + ":" + name]
            )
            check(
                hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == blob
            )


def lookup(data, wanted):
    """Read selected GGUF token strings/types only. No tensor or model construction."""
    f = io.BytesIO(data)

    def num(fmt):
        return struct.unpack("<" + fmt, f.read(struct.calcsize("<" + fmt)))[0]

    def string():
        return f.read(num("Q"))

    check(f.read(4) == b"GGUF" and num("I") == 3 and num("Q") == 0)
    sizes = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
    tok, typ = {}, {}
    for _ in range(num("Q")):
        field, kind = string(), num("I")
        if kind == 8:
            string()
        elif kind == 9:
            item, count = num("I"), num("Q")
            if item == 8:
                for i in range(count):
                    s = string()
                    if field == b"tokenizer.ggml.tokens" and i in wanted:
                        tok[i] = s.decode()
            else:
                pos = f.tell()
                if field == b"tokenizer.ggml.token_type":
                    check(item == 5)
                    for i in wanted:
                        check(0 <= i < count)
                        f.seek(pos + i * 4)
                        typ[i] = num("i")
                f.seek(pos + sizes[item] * count)
        else:
            f.seek(sizes[kind], 1)
    # Inverse byte alphabet of llama.cpp's GPT-2 BPE. Kept IDs come solely from SSE/request.
    alphabet = list(range(33, 127)) + list(range(161, 173)) + list(range(174, 256))
    extra = [n for n in range(256) if n not in alphabet]
    inverse = {chr(n): n for n in alphabet} | {chr(256 + i): n for i, n in enumerate(extra)}
    check(set(tok) == set(typ) == wanted)
    return {
        i: (typ[i], bytes(inverse[c] for c in tok[i]) if typ[i] == 1 else tok[i].encode())
        for i in wanted
    }


def canonical(parts):
    # The C75 text PEG and the stock token-aware PEG agree only on this restricted production.
    # Both map the entire reasoning/content node verbatim. Whitespace-only reasoning is discarded.
    # No partial marker, tool, commentary, sanitization or finalization is admitted.
    if len(parts) < 4 or parts[0] not in [(3, b"<|channel|>"), (4, b"<|channel|>")]:
        return None
    combined = b"".join(b for _, b in parts)
    match = re.fullmatch(rb"<\|channel\|>(analysis|final)<\|message\|>([^<>]+)", combined)
    if not match:
        return None
    try:
        match[2].decode("utf-8")
    except UnicodeDecodeError:
        return None
    i = next((i for i, p in enumerate(parts[1:], 1) if p[0] != 1), -1)
    if i < 2 or parts[i] not in [(3, b"<|message|>"), (4, b"<|message|>")]:
        return None
    body = b"".join(b for _, b in parts[i + 1 :])
    if any(t != 1 for t, _ in parts[i + 1 :]) or body != match[2] or not body.strip(b" \t\r\n"):
        return None
    return ("reasoning_content" if match[1] == b"analysis" else "content", body)


def compare(parts, historical):
    parsed = canonical(parts)
    if parsed is None:
        return {"class": "INCONCLUSIVE", "reason": "unqualified_partial_grammar"}
    name, body = parsed
    h = historical[name].encode()
    ref = h[: len(body)]
    pos = next((i for i, (a, b) in enumerate(zip(body, ref, strict=False)) if a != b), None)
    if pos is None and len(ref) < len(body):
        pos = len(ref)
    return {
        "class": "visible_prefix_diverges" if pos is not None else "prefix_visible_equal",
        "channel": name,
        "stock_bytes": len(body),
        "historical_prefix_bytes": len(ref),
        "stock_sha256": sha(body),
        "historical_prefix_sha256": sha(ref),
        "first_difference_zero_based": pos,
    }


def run(history, raw, vocab, backends):
    source_check(backends)
    receipt = json.loads(checked(BASE / "aster_turn2_budget/physical-r1/receipt.json", RECEIPT))
    source = (
        history / "c133-diverse-active-session-20260929T2000Z/raw/c133-c75-slots40-diverse20.json"
    )
    message = json.loads(checked(source, C133))["results"][1]["message"]
    request = json.loads(checked(raw / "T2.request.json", receipt["raw_sha256"]["T2.request.json"]))
    prompt = request["prompt"]
    check(len(prompt) == 435 and request["n_predict"] == 8)
    check(
        sha(json.dumps(prompt, separators=(",", ":")).encode())
        == receipt["after_ready"]["official_T2_ids_sha256"]
    )
    stream = checked(raw / "T2.sse", receipt["raw_sha256"]["T2.sse"])
    events = [json.loads(s[6:]) for s in stream.splitlines() if s.startswith(b"data: ")]
    check(len(events) == 9 and events[-1]["stop"] and events[-1]["stop_type"] == "limit")
    ids = []
    for i, e in enumerate(events[:-1], 1):
        check(
            e["stop"] is False
            and e["tokens_predicted"] == i
            and len(e["tokens"]) == 1
            and e["timings"]["cache_n"] == 122
            and e["timings"]["prompt_n"] == 313
        )
        ids.extend(e["tokens"])
    vocab_map = lookup(checked(vocab, VOCAB), set(ids + prompt[-2:]))
    check(vocab_map[prompt[-2]][1] == b"<|start|>" and vocab_map[prompt[-1]] == (1, b"assistant"))
    parts = [vocab_map[t] for t in ids]
    result = compare(parts, message)
    return {
        **result,
        "stock_raw_sha256": sha(stream),
        "c133_sha256": C133,
        "vocab_sha256": VOCAB,
        "stock_receipt_sha256": RECEIPT,
        "observed_tokens": len(ids),
        "model_forwards": 0,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for arg in ["historical-results", "stock-raw", "vocab", "native-backends", "new-output-dir"]:
        p.add_argument("--" + arg, type=Path, required=True)
    args = p.parse_args()
    args.new_output_dir.mkdir(parents=True, exist_ok=False)
    try:

        def git(*params):
            return subprocess.check_output(
                ["git", "--no-optional-locks", "-C", str(HERE), *params], text=True
            ).strip()

        check(not git("status", "--porcelain"))
        result = run(args.historical_results, args.stock_raw, args.vocab, args.native_backends)
        result.update(
            measurement_commit=git("rev-parse", "HEAD"),
            tree=git("rev-parse", "HEAD^{tree}"),
            program_sha256=sha(Path(__file__).read_bytes()),
            protocol_sha256=sha((HERE / "protocol.md").read_bytes()),
        )
    except Exception as exc:
        (args.new_output_dir / "FAIL.json").write_text(
            json.dumps({"class": "INCONCLUSIVE", "failure": type(exc).__name__})
        )
        raise SystemExit(1) from None
    (args.new_output_dir / "receipt.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n"
    )
