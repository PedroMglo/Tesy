"""C85 request marker controls, including an interrupted second request."""

import json
import tempfile
import unittest
from pathlib import Path

from c2_gate import GateError
from c85_request_markers import validate


class RequestMarkerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'markers.jsonl'
        self.rows = [
            {'schema':'c85-request-monotonic-v1','run_id':'run','request_id':rid,
             'kind':kind,'mono_ns':ns}
            for rid,kind,ns in [('first','REQUEST_START',100),
                                ('first','RESPONSE_COMPLETE',200),
                                ('second','REQUEST_START',300),
                                ('second','RESPONSE_COMPLETE',400)]]
        self.raw = [{'id':rid,'monotonic_request_markers_ns':{
            'request_start':start,'response_complete':end}}
            for rid,start,end in [('first',100,200),('second',300,400)]]

    def check(self, rows=None, raw=None, **kwargs):
        self.path.write_text(''.join(json.dumps(row)+'\n' for row in (rows if rows is not None else self.rows)))
        return validate(self.path,'run',['first','second'],self.raw if raw is None else raw,**kwargs)

    def test_complete(self):
        self.assertEqual(self.check()['complete_pairs'],2)

    def test_interrupted_second_is_incomplete(self):
        self.assertEqual(self.check(self.rows[:-1],self.raw[:1],require_complete=False)['status'],
                         'INCOMPLETE_EVIDENCE')
        with self.assertRaises(GateError):
            self.check(self.rows[:-1],self.raw[:1])

    def test_overlap_duplicate_and_wrong_raw(self):
        rows=[dict(x) for x in self.rows]
        rows[2]['mono_ns']=150
        with self.assertRaises(GateError):self.check(rows)
        with self.assertRaises(GateError):self.check(self.rows+[self.rows[-1]])
        with self.assertRaises(GateError):self.check(raw=self.raw[:1])

    def test_numeric_overflow_and_bool(self):
        rows=[dict(x) for x in self.rows]
        rows[0]['mono_ns']=True
        with self.assertRaises(GateError):self.check(rows)
        self.path.write_text(self.path.read_text().replace('true','1e309',1))
        with self.assertRaises(GateError):
            validate(self.path,'run',['first','second'],self.raw)


if __name__ == '__main__':
    unittest.main()
