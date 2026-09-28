import unittest

from c2_gate import GateError
from c2_server_run import assistant_history_messages


class AssistantHistoryTests(unittest.TestCase):
    def test_actual_content_is_included_exactly(self):
        first = [{'role': 'user', 'content': 'Remember code 4372.'}]
        answer = {'role': 'assistant', 'content': 'Stored 4372.',
                  'reasoning_content': 'private diagnostic field'}
        next_turn = [{'role': 'user', 'content': 'Which code?'}]
        self.assertEqual(assistant_history_messages(first, answer, next_turn),
                         [first[0], {'role': 'assistant', 'content': 'Stored 4372.'},
                          next_turn[0]])
        self.assertEqual(first, [{'role': 'user', 'content': 'Remember code 4372.'}])

    def test_empty_final_content_is_rejected(self):
        with self.assertRaises(GateError):
            assistant_history_messages([{'role':'user','content':'A'}],
                                       {'role':'assistant','content':''},
                                       [{'role':'user','content':'B'}])

    def test_wrong_role_is_rejected(self):
        with self.assertRaises(GateError):
            assistant_history_messages([{'role':'user','content':'A'}],
                                       {'role':'user','content':'fabricated'},
                                       [{'role':'user','content':'B'}])
