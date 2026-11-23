"""Focused checks for C123 raw identity and causal cache ordering."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from c2_gate import GateError
from c123_analyze_trace import analyze, simulate_completed_lru


class C123AnalysisTest(unittest.TestCase):
    def test_completed_load_required_for_cache_hit(self):
        layers = {0: {'bytes': 100, 'device': 'CPU'}}
        def e(kind, t, seq):
            return {'kind': kind, 'mono_us': t, 'seq': seq, 'layer': 0,
                    'expert': 1, 'call_id': 3}
        rows = [e('LOAD_BEGIN', 1, 0), e('LOAD_BEGIN', 2, 1),
                e('LOAD_END', 3, 2), e('LOAD_BEGIN', 4, 3)]
        result = simulate_completed_lru(rows, layers, 100)
        self.assertEqual(result['load_counts']['decode'], 3)
        self.assertEqual(result['hits']['decode'], 1)

    def test_frozen_trace_and_marker_controls(self):
        source = Path(__file__).resolve().parents[1] / 'results/c123-warm153-decode-trace-20260929T1450Z'
        if not (source / 'raw/c123-c75-warm153.expert.trace').exists():
            self.skipTest('local C123 raw unavailable')
        self.assertEqual(analyze(source)['tokens']['new_prompt'], 153)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'raw').mkdir()
            for name in ('expert.trace', 'json', 'receipt.json', 'request-markers.jsonl', 'trace-trigger.json'):
                filename = 'c123-c75-warm153.' + name
                shutil.copy2(source / 'raw' / filename, root / 'raw' / filename)
            raw = root / 'raw/c123-c75-warm153.json'
            raw.write_bytes(raw.read_bytes() + b' ')
            with self.assertRaisesRegex(GateError, 'SHA mismatch'):
                analyze(root)
            shutil.copy2(source / 'raw/c123-c75-warm153.json', raw)
            markers = root / 'raw/c123-c75-warm153.request-markers.jsonl'
            lines = markers.read_text().splitlines()
            row = json.loads(lines[2]); row['request_id'] = 'wrong-arm'
            lines[2] = json.dumps(row)
            markers.write_text('\n'.join(lines) + '\n')
            with self.assertRaisesRegex(GateError, 'marker order/identity'):
                analyze(root)


if __name__ == '__main__':
    unittest.main()
