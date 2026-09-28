"""Small positive/negative diagnostic trace receipts, no model."""

import tempfile
import unittest
from pathlib import Path

from c2_gate import GateError
from c84_trace_validate import EXPERT_BYTES, validate


def fixture():
    lines = ['#c84-expert-demand-v1',
             '#layer\tlayer\tlogical_expert_bytes\tbuffer_name']
    lines += [f'L\t{i}\t{EXPERT_BYTES}\tCPU' for i in range(36)]
    lines.append('kind\tseq\tmono_us\tlayer\texpert\tslot\tvictim\tn_tokens\twave\tstate\tlogical_bytes')
    lines += [
        'DEMAND\t0\t100\t0\t7\t-1\t-1\t1\t-1\t0\t0',
        'RESERVE\t1\t101\t0\t7\t0\t-1\t0\t-1\t-1\t0',
        'WAIT_BEGIN\t2\t102\t0\t-1\t-1\t-1\t1\t-1\t-1\t0',
        f'LOAD_BEGIN\t3\t103\t0\t7\t0\t-1\t0\t-1\t-1\t{EXPERT_BYTES}',
        f'LOAD_END\t4\t120\t0\t7\t0\t-1\t0\t-1\t-1\t{EXPERT_BYTES}',
        'WAIT_END\t5\t121\t0\t-1\t-1\t-1\t1\t-1\t-1\t0',
        'DEMAND\t6\t200\t0\t7\t0\t-1\t1\t-1\t2\t0',
        '#end\t7\t0',
    ]
    return lines


class TraceReceiptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'trace.tsv'

    def check(self, lines):
        self.path.write_text('\n'.join(lines) + '\n')
        return validate(self.path)

    def test_valid(self):
        result = self.check(fixture())
        self.assertEqual((2, 1, 1), (result['demand_events'],
                                   result['load_pairs'], result['wait_pairs']))

    def test_missing_footer_and_overflow(self):
        with self.assertRaises(GateError):
            self.check(fixture()[:-1])
        lines = fixture()
        lines[-1] = '#end\t7\t1'
        with self.assertRaises(GateError):
            self.check(lines)

    def test_duplicate_layer(self):
        lines = fixture()
        lines[3] = lines[2]
        with self.assertRaises(GateError):
            self.check(lines)

    def test_bad_demand_and_load_pair(self):
        lines = fixture()
        lines[39] = lines[39].replace('\t0\t7\t-1\t-1\t1\t-1\t0\t0',
                                      '\t0\t128\t-1\t-1\t1\t-1\t0\t0')
        with self.assertRaises(GateError):
            self.check(lines)
        lines = fixture()
        lines[43] = lines[43].replace(f'\t{EXPERT_BYTES}', '\t4')
        with self.assertRaises(GateError):
            self.check(lines)

    def test_trailing_data(self):
        lines = fixture() + ['extra']
        with self.assertRaises(GateError):
            self.check(lines)


if __name__ == '__main__':
    unittest.main()
