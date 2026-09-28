import unittest

from c2_gate import GateError
from c2_server_run import assistant_history_messages, validate_generated_prefix_cache


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

    def test_third_turn_retains_both_actual_answers(self):
        first = [{'role':'user','content':'A'}]
        second = assistant_history_messages(first,
                    {'role':'assistant','content':'12345'},
                    [{'role':'user','content':'B'}])
        third = assistant_history_messages(second,
                    {'role':'assistant','content':'12345'},
                    [{'role':'user','content':'C'}])
        self.assertEqual([item['role'] for item in third],
                         ['user','assistant','user','assistant','user'])
        self.assertEqual([third[1]['content'],third[3]['content']],['12345','12345'])
        self.assertEqual(first,[{'role':'user','content':'A'}])

    def test_missing_or_malformed_history_rejected(self):
        next_turn = [{'role':'user','content':'C'}]
        answer = {'role':'assistant','content':'12345'}
        for history in ([],[{'role':'assistant','content':'A'}],
                        [{'role':'user','content':'A'},
                         {'role':'assistant','content':'12345'}],
                        [{'role':'user','content':'A'},
                         {'role':'assistant','content':''},
                         {'role':'user','content':'B'}]):
            with self.subTest(history=history), self.assertRaises(GateError):
                assistant_history_messages(history,answer,next_turn)

    def test_generated_token_cache_bound_and_accounting(self):
        old = list(range(2043))
        new = old + [2043, 2044, 2045]
        self.assertEqual(validate_generated_prefix_cache(old,new,2044,2,77,1900),2043)
        for cache_n,prompt_n,completion_n in ((2044,1,77),
                                                (2121,-75,77),
                                                (2044,2,0),
                                                (2000,46,77)):
            with self.subTest(cache_n=cache_n,prompt_n=prompt_n), self.assertRaises(GateError):
                validate_generated_prefix_cache(old,new,cache_n,prompt_n,completion_n,1900)
