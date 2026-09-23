from tesy.server_client import _parse_sse_line


def test_sse_parser_ignores_comments():
    assert _parse_sse_line(b": ping\n") is None


def test_sse_parser_decodes_object():
    assert _parse_sse_line(b'data: {"content":"x"}\n') == {"content": "x"}


def test_sse_parser_ignores_done():
    assert _parse_sse_line(b"data: [DONE]\n") is None
