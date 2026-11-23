import json
from pathlib import Path
import tempfile
import time
import unittest
from request_evidence import Deadline, Evidence
from c2_server_run import parse_chat_stream

class RequestEvidenceTests(unittest.TestCase):
    def test_completion_before_after_and_at_deadline(self):
        for completed,valid in [(9.99,True),(10,False),(10.01,False)]:
            clock=[completed];cancel=[]
            d=Deadline(10,lambda:cancel.append(clock[0]),clock=lambda:clock[0])
            self.assertEqual(d.complete(completed),valid)
            self.assertEqual(len(cancel),not valid)
        # Timer first, then transport still returns a complete late response.
        clock=[10];cancel=[];d=Deadline(10,lambda:cancel.append(1),clock=lambda:clock[0])
        self.assertTrue(d.check());self.assertFalse(d.complete(10.01));self.assertEqual(cancel,[1])

    def test_independent_timer_no_chunks_and_continuous_chunks(self):
        for continuous in (False,True):
            cancelled=[];start=time.monotonic();d=Deadline(start+.15,lambda:cancelled.append(time.monotonic()));d.start()
            while time.monotonic()-start<.25:
                if continuous:pass # no progress can extend the watchdog
                time.sleep(.003)
            result=d.finish();self.assertEqual(len(cancelled),1)
            self.assertLess(cancelled[0]-(start+.15),.250)
            self.assertFalse(result['watchdog_alive'])

    def test_partial_stream_retained_with_interruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'request.jsonl';e=Evidence(path,'first',time.monotonic(),1)
            chunk=b'data: {"choices":[{"delta":{"content":"partial"}}]}\n'
            def lines():
                e.write('SSE_FRAGMENT',fragment=chunk.decode());yield chunk
                raise ConnectionError('cancelled')
            with self.assertRaises(ConnectionError):parse_chat_stream(lines(),lambda:.1)
            e.write('REQUEST_TERMINAL',accepted=False,invalid_reason='cancelled',transport_complete=False);e.close()
            rows=[json.loads(x) for x in path.read_text().splitlines()]
            self.assertIn('partial',rows[1]['fragment']);self.assertFalse(rows[-1]['accepted'])

    def test_evidence_cap_is_explicit_and_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'raw';e=Evidence(path,'first',0,1,cap=4096)
            with self.assertRaisesRegex(ValueError,'CAP_EXCEEDED'):e.write('SSE_FRAGMENT',fragment='x'*4096)
            self.assertTrue(e.truncated);e.close();self.assertLess(path.stat().st_size,4096)
            self.assertEqual(json.loads(path.read_text().splitlines()[-1])['kind'],'EVIDENCE_TRUNCATED')

    def test_cancel_error_is_not_silently_accepted(self):
        def fail():raise RuntimeError('identity changed; no signal')
        d=Deadline(0,fail);d.check();self.assertIn('identity changed',d.cancel_error)

if __name__=='__main__':unittest.main()
