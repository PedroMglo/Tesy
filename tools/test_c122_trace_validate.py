import tempfile
import unittest
from pathlib import Path

from c2_gate import GateError
from c122_trace_validate import validate


class TraceGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'trace.tsv'

    def write(self, rows, *, overflow=0):
        header = 'kind\tseq\tmono_us\tlayer\texpert\tslot\tvictim\tn_tokens\twave\tstate\tlogical_bytes\tcall_id\tgeneration\tcomponent'
        text = ['#c122-expert-decode-v1', '#layer\tlayer\tlogical_expert_bytes\tbuffer_name',
                'L\t25\t128\tCUDA', header]
        text += ['\t'.join(map(str, [kind, i, when, layer, expert, slot, -1,
                                      tokens, -1, -1, size, 1, gen, component]))
                 for i, (kind, when, layer, expert, slot, tokens, size, gen, component)
                 in enumerate(rows)]
        text.append(f'#end\t{len(rows)}\t{overflow}')
        self.path.write_text('\n'.join(text)+'\n')

    def rows(self):
        return [('CALL_BEGIN',100,-1,2044,2075,32,0,0,-1),
                ('ENQUEUE',101,25,7,3,0,0,9,-1),
                ('DEQUEUE',110,25,7,3,0,0,9,-1),
                ('LOAD_BEGIN',111,25,7,3,0,128,9,-1),
                ('READ_BEGIN',112,25,7,3,0,64,9,0),
                ('READ_END',120,25,7,3,0,64,9,0),
                ('TENSOR_SET_BEGIN',121,25,7,3,0,64,9,0),
                ('TENSOR_SET_RETURN',130,25,7,3,0,64,9,0),
                ('LOAD_END',131,25,7,3,0,128,9,-1),
                ('CALL_END',140,-1,2044,2075,32,0,0,-1)]

    def test_complete(self):
        self.write(self.rows())
        row = validate(self.path)
        self.assertEqual(row['events'], 10)
        self.assertEqual(row['loads'], 1)
        self.assertEqual(row['span_union_us']['READ_BEGIN'], 8)

    def test_orphan_end(self):
        rows = self.rows(); rows.pop(4)
        self.write(rows)
        with self.assertRaises(GateError): validate(self.path)

    def test_duplicate_end(self):
        rows = self.rows(); rows.insert(6, rows[5])
        self.write(rows)
        with self.assertRaises(GateError): validate(self.path)

    def test_negative_interval(self):
        rows = self.rows(); rows[5] = (*rows[5][:1], 111, *rows[5][2:])
        self.write(rows)
        with self.assertRaises(GateError): validate(self.path)

    def test_overflow(self):
        self.write(self.rows(), overflow=1)
        with self.assertRaises(GateError): validate(self.path)

    def test_missing_call_end(self):
        self.write(self.rows()[:-1])
        with self.assertRaises(GateError): validate(self.path)


if __name__ == '__main__': unittest.main()
