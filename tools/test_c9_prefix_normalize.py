"""Check cached prompt accounting against independent server timing counts."""

import copy
import unittest

from c2_gate import GateError
from c2_server_run import normalize


class PrefixNormalizationTests(unittest.TestCase):
    def fixture(self):
        raw = []
        for row_id, total, cached, prompt_ms in (
            ('prefix', 512, 0, 100.0), ('suffix', 640, 511, 25.0)):
            raw.append({'id': row_id, 'started_s': 0, 'ended_s': 1,
                        'usage': {'prompt_tokens': total, 'completion_tokens': 4,
                                  'total_tokens': total+4,
                                  'prompt_tokens_details': {'cached_tokens': cached}},
                        'timings': {'cache_n': cached, 'prompt_ms': prompt_ms,
                                    'predicted_ms': 10.0}, 'finish_reason': 'length'})
        stderr = ('slot print_timing: id 0 | task 0 | prompt eval time = 100.000 ms / 512 tokens\n'
                  'slot print_timing: id 0 | task 0 | eval time = 10.000 ms / 4 tokens\n'
                  'slot print_timing: id 0 | task 1 | prompt eval time = 25.000 ms / 129 tokens\n'
                  'slot print_timing: id 0 | task 1 | eval time = 10.000 ms / 4 tokens\n')
        config = {'suite': 'c9prefix', 'run_id': 'synthetic', 'allow_cache_prompt': True,
                  'enforce_output_reserve': True, 'n_ctx': 8192,
                  'request_policy': {'max_tokens': 4}}
        protocol = {'campaign_id': 'synthetic', 'protocol_id': 'synthetic',
                    'identity': {}, 'expected_request_ids': [], 'limits': {}}
        return raw, stderr, config, protocol

    def test_valid_cached_second_request(self):
        raw, stderr, config, protocol = self.fixture()
        doc = normalize(raw, protocol, config, [], stderr, 2, 0, [])
        self.assertEqual(doc['requests'][1]['backend_prompt_tokens'], 640)
        self.assertEqual(doc['requests'][1]['prefill_s'], .025)

    def test_cached_count_disagreement_and_unfrozen_cache(self):
        raw, stderr, config, protocol = self.fixture()
        bad = copy.deepcopy(raw)
        bad[1]['usage']['prompt_tokens_details']['cached_tokens'] = 510
        with self.assertRaisesRegex(GateError, 'prefix cache reuse'):
            normalize(bad, protocol, config, [], stderr, 2, 0, [])
        config['allow_cache_prompt'] = False
        with self.assertRaisesRegex(GateError, 'prefix cache reuse'):
            normalize(raw, protocol, config, [], stderr, 2, 0, [])


if __name__ == '__main__':
    unittest.main()
