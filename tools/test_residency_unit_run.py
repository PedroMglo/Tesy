"""Family ordering and immutable freeze; mature entrypoint tests cover child gate."""
import json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import residency_unit_run as r
class FamilyTests(unittest.TestCase):
 def protocol(self):
  return {'physical_envelope_s':400,'common_env':{'TESY_CPU_WAVE_SKIP_PARKED':'1'},'backend_root':'/fixture','model_id':'locked-model','claim_scope':'fixture','success_status':'PASS','runs':[{'id':str(i),'timeout_s':10,'inventory':True,'env':{},'variant':'44','label':'fixed','command':['/bin/true']} for i in range(4)]}
 def test_positive_four_external_launches(self):
  with tempfile.TemporaryDirectory() as d,patch.object(r.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'','')) as spawn:
   self.assertEqual(r.inside(Path('/fixture'),Path(d),self.protocol()),0)
   self.assertEqual(spawn.call_count,4)
   for call in spawn.call_args_list:self.assertIn('--collect-start-inventory',call.args[0]);self.assertIn('--resource-protocol',call.args[0])
 def test_external_gate_failure_stops_every_position(self):
  for at in range(4):
   with self.subTest(at=at),tempfile.TemporaryDirectory() as d,patch.object(r.subprocess,'run',side_effect=[subprocess.CompletedProcess([],0,'','')]*at+[subprocess.CompletedProcess([],1,'','NOT_ADMITTED')]) as spawn:
    self.assertEqual(r.inside(Path('/fixture'),Path(d),self.protocol()),1)
    self.assertEqual(spawn.call_count,at+1);self.assertEqual(len(list(Path(d).glob('*-attempt.json'))),at+1)
 def test_envelope_blocks_before_external_process(self):
  p=self.protocol();p['physical_envelope_s']=80
  with tempfile.TemporaryDirectory() as d,patch.object(r.subprocess,'run') as spawn:
   self.assertEqual(r.inside(Path('/fixture'),Path(d),p),1);spawn.assert_not_called()
 def test_atomic_no_replace(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'receipt.json';r.publish(p,{'original':1})
   with self.assertRaises(FileExistsError):r.publish(p,{'original':2})
   self.assertEqual(json.loads(p.read_text()),{'original':1})
if __name__=='__main__':unittest.main()
