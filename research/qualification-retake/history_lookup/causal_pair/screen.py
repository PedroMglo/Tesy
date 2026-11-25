"""Frozen causal longest recently matched exact N=2 -> M=2, or N=1 -> M=1."""

import argparse
import hashlib
import json
import struct
from pathlib import Path

if not __debug__:
    raise RuntimeError("run with Python assertions enabled")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pinned(p, h):
    b = p.read_bytes()
    assert digest(b) == h, p.name
    return json.loads(b)


def draft(history, n, m):
    # C269 ngram-map.cpp: tokens excludes sampled; fallback only via ordinary AR.
    cur = len(history) - 1
    if cur <= n + m + 1:
        return ()
    pattern = history[-n:]
    for j in range(cur - n - 1, 0, -1):
        if history[j : j + n] == pattern:
            k = min(m, cur - (j + n))
            return history[j + n : j + n + k] if k >= n else ()
    return ()


def replay(prompt, target, n, m):
    history = tuple(prompt) + tuple(target[:1])
    xs = tuple(target[1:])
    pos = calls = proposals = drafted = accept = bonus = full = ar = rej = 0
    while pos < len(xs):
        # The entire function that chooses proposals gets only confirmed history.
        d = draft(history, n, m)
        calls += 1
        proposals += bool(d)
        ar += not bool(d)
        drafted += len(d)
        confirmed = 0
        for v in d:
            if pos + confirmed == len(xs):
                break
            if v != xs[pos + confirmed]:
                rej += 1
                break
            confirmed += 1
        full += bool(d) and confirmed == len(d)
        accept += confirmed
        extra = int(pos + confirmed < len(xs))
        bonus += extra
        advance = confirmed + extra
        assert advance and xs[pos : pos + confirmed] == tuple(d[:confirmed])
        history += xs[pos : pos + advance]
        pos += advance
    assert (
        history == tuple(prompt) + tuple(target)
        and accept + bonus == pos
        and calls == proposals + ar
    )
    return dict(
        outputs=pos,
        calls=calls,
        ordinary=ar,
        proposals=proposals,
        drafted_ids=drafted,
        accepted_ids=accept,
        full_proposals=full,
        rejections=rej,
        ordinary_corrective_or_bonus=bonus,
        fewer_calls=pos - calls,
    )


def main(root, lab, natural):
    cert_n = pinned(
        root / "research/qualification-retake/nvme_conversation/evidence-20261124-r1/evidence.json",
        "f64067231b0936d82ce822ca782adfdb00bb9134b60d46fdc6a5bac3e6d64f74",
    )
    artifacts = {}
    for n in ["T2-input.json", "T2-result.json", "T2-request.jsonl"]:
        b = (natural / "raw" / n).read_bytes()
        mark = cert_n["local_manifest"]["raw/" + n]
        assert len(b) == mark["bytes"] and digest(b) == mark["sha256"]
        artifacts[n] = b
    live = json.loads(artifacts["T2-result.json"])
    orig = json.loads(artifacts["T2-input.json"])["official_ids"]
    assert (
        live["official_ids"] == orig
        and live["output_ids"] is None
        and live["output_ids_authority"] == "NOT_EXPOSED_EMPTY_OR_ABSENT"
    )
    assert live["usage"]["completion_tokens"] == 47
    chunks = [json.loads(row) for row in artifacts["T2-request.jsonl"].splitlines()]
    sse = [r["fragment"].strip() for r in chunks if r["kind"] == "SSE_FRAGMENT"]
    frames = [json.loads(x[6:]) for x in sse if x.startswith("data: ") and x != "data: [DONE]"]
    verbose = [r["__verbose"]["tokens"] for r in frames if "__verbose" in r]
    assert len(sse) == 81 and verbose == [[]]
    output = {
        "classification": "INCONCLUSIVE_ON_NATURAL_OUTPUT_IDS",
        "natural_completion_count": 47,
        "natural_native_output_ids_exposed": False,
        "historical_cases": [],
    }

    fix = pinned(
        root / "results/c244-multigrid-continuity-20261004/development-native-inputs.json",
        "788020f22322bc4a6d90cfdf1e05b3554dd31804c2d72d795e13af9eb9a7754d",
    )
    cert = pinned(
        root / "results/c242-native-control-mapping-repair-20261004/control-ids-summary.json",
        "375faa13df34602536c9fd379de952f5bfaea6f88dcf610592300e4a98b145d1",
    )
    assert (
        digest((lab / "backends/c269-layer-last-use/common/ngram-map.cpp").read_bytes())
        == "4bedd358b43833f6f10bd11c254da7b5bcae779fc58a4f577032cc0b3a9a4732"
    )
    for c in cert["cases"]:
        name = c["case"]
        b = pinned(
            lab
            / "results/c242-native-control-mapping-repair-20261004/raw"
            / ("c242-" + name + ".native")
            / "result.json",
            c["receipt_sha256"],
        )
        p = b["official_prefix_ids"]
        t = b["native_generated_ids"]
        assert p == fix[name]["ids"] and t == fix[name]["continuation_ids"]
        assert (
            len(t) == c["count"]
            and b["finish"] == c["finish"]
            and b["status"] == "NATIVE_CONTROL_IDS_CAPTURED"
        )
        if name == "anchor-nominal153":
            assert (
                digest(struct.pack("<" + "i" * len(p), *p))
                == "a47a9cecb5f57aef177f59fe5653a55c0b5fba10fd9f4c6905663df3b2aa3b50"
            )  # C188 only; C281 identity failed.
            different = [i for i, (x, y) in enumerate(zip(p, orig, strict=True)) if x != y]
            assert different == [33, 35]
            output["nominal_prompt_positions_different_zero_based"] = different
        for end in sorted({33, len(t)}):
            for k in (1, 2):
                output["historical_cases"].append(
                    dict(
                        case=name,
                        n=k,
                        m=k,
                        window=end - 1,
                        stop=b["finish"] if end == len(t) else "diagnostic_32",
                        **replay(p, t[:end], k, k),
                    )
                )

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("repo", "lab", "natural-root", "new-output-dir"):
        parser.add_argument("--" + key, type=Path, required=True)
    a = parser.parse_args()
    a.new_output_dir.mkdir(mode=0o700, exist_ok=False)
    try:
        result = main(a.repo, a.lab, a.natural_root)
    except Exception as exc:
        with (a.new_output_dir / "failure.json").open("x") as f:
            json.dump({"status": "FAIL_PRESERVED", "exception": type(exc).__name__}, f)
        raise
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2)
        f.write("\n")
