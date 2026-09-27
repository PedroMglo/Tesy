import json
import unittest

from c2_gate import GateError
from c2_server_run import parse_chat_stream


def event(value):
    return ('data: ' + json.dumps(value) + '\n').encode()


class ChatStreamTest(unittest.TestCase):
    def test_reasoning_then_final_with_usage_and_completion_fence(self):
        lines = [
            event({'choices': [{'delta': {'role': 'assistant'}, 'finish_reason': None}]}),
            event({'choices': [{'delta': {'reasoning_content': 'thinking'}, 'finish_reason': None}]}),
            event({'choices': [{'delta': {'content': ' answer'}, 'finish_reason': None}]}),
            event({'choices': [{'delta': {}, 'finish_reason': 'stop'}]}),
            event({'choices': [], 'usage': {'prompt_tokens': 10, 'completion_tokens': 2},
                   'timings': {'cache_n': 8}}),
            b'data: [DONE]\n',
        ]
        moments = iter([1.5, 2.25])
        response, metrics = parse_chat_stream(lines, lambda: next(moments))
        self.assertEqual(response['choices'][0]['message'],
                         {'role': 'assistant', 'content': ' answer',
                          'reasoning_content': 'thinking'})
        self.assertEqual(response['timings']['cache_n'], 8)
        self.assertEqual(metrics['first_text_chunk_s'], 1.5)
        self.assertEqual(metrics['first_reasoning_chunk_s'], 1.5)
        self.assertEqual(metrics['first_final_content_chunk_s'], 2.25)
        self.assertTrue(metrics['done_observed'])

    def test_missing_done_or_usage_fails_instead_of_timing_partial_stream(self):
        base = [event({'choices': [{'delta': {'content': 'OK'}, 'finish_reason': None}]}),
                event({'choices': [{'delta': {}, 'finish_reason': 'stop'}]}),
                event({'choices': [], 'usage': {}, 'timings': {}})]
        for lines in (base, base[:2] + [b'data: [DONE]\n']):
            with self.subTest(lines=lines), self.assertRaisesRegex(GateError, 'incomplete stream'):
                parse_chat_stream(lines, lambda: 1.0)

    def test_tool_call_and_numeric_overflow_fail(self):
        with self.assertRaisesRegex(GateError, 'tool call'):
            parse_chat_stream([event({'choices': [{'delta': {'tool_calls': [{'index': 0}]},
                                                        'finish_reason': None}]})], lambda: 1.0)
        with self.assertRaises(ValueError):
            parse_chat_stream([b'data: {"choices":[],"usage":{"x":1e309}}\n'], lambda: 1.0)
