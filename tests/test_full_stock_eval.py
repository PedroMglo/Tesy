import json

import pytest

from tesy.full_stock_eval import parse_chat_stream


def _stream(*, done=True, predicted_n=1, timing=12.0):
    chunks = [
        {"choices": [{"delta": {"content": "olá"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "length"}]},
        {
            "choices": [],
            "usage": {"prompt_tokens": 7, "completion_tokens": 1},
            "timings": {
                "prompt_ms": 2.0,
                "predicted_ms": timing,
                "predicted_per_token_ms": timing,
                "predicted_n": predicted_n,
            },
        },
    ]
    lines = [f"data: {json.dumps(chunk)}\n".encode() for chunk in chunks]
    if done:
        lines.append(b"data: [DONE]\n")
    return lines


def test_parse_chat_stream_complete():
    content, usage, timings, reason = parse_chat_stream(_stream())
    assert content == "olá"
    assert usage["completion_tokens"] == timings["predicted_n"] == 1
    assert reason == "length"


@pytest.mark.parametrize("lines", [
    _stream(done=False),
    _stream(predicted_n=2),
    _stream(timing=float("nan")),
])
def test_parse_chat_stream_rejects_invalid(lines):
    with pytest.raises(ValueError):
        parse_chat_stream(lines)
