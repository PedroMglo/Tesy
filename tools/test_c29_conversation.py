import unittest

from c2_gate import GateError
from c29_conversation_bridge import validate_conversation_cache


class ConversationCacheBoundTest(unittest.TestCase):
    def test_generated_slot_token_can_extend_original_prompt_prefix(self):
        validate_conversation_cache(2035, 2179, 52, 2035, 2036, 143)

    def test_impossible_or_unaccounted_cache_fails(self):
        for cache_n, processed_n in ((2088, 91), (2002, 177), (2036, 142)):
            with self.subTest(cache_n=cache_n, processed_n=processed_n), self.assertRaises(GateError):
                validate_conversation_cache(2035, 2179, 52, 2035, cache_n, processed_n)


if __name__ == '__main__':
    unittest.main()
