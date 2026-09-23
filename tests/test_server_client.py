import pytest

from tesy.server_client import ServerClientError, _event_token_ids, _parse_sse_line


def test_sse_parser_ignores_comments():
    assert _parse_sse_line(b": ping\n") is None


def test_sse_parser_decodes_object():
    assert _parse_sse_line(b'data: {"content":"x"}\n') == {"content": "x"}


def test_sse_parser_ignores_done():
    assert _parse_sse_line(b"data: [DONE]\n") is None


def test_event_token_ids_accepts_integer_list():
    assert _event_token_ids({"tokens": [1, 2, 3]}) == [1, 2, 3]


def test_event_token_ids_allows_missing_tokens():
    assert _event_token_ids({}) == []


def test_event_token_ids_rejects_bool():
    with pytest.raises(ServerClientError):
        _event_token_ids({"tokens": [True]})
