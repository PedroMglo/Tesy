import tempfile,unittest,json,subprocess,struct
from pathlib import Path
from mmap_phase_gate import PHASES,payload,compare_logits,logits,inspect
ROOT=Path(__file__).resolve().parents[1]
BIN=ROOT/'results/c165-mmap-phase-preparation-20260930T1210Z/build/mmap_phase_probe'
class SmallNativeGate(unittest.TestCase):
 def test_alias_shape_is_actual_raw_scores(self):
  row={'phase':'prefill0','name':'ffn_moe_logits_biased','type':'f32','ne':'128,32,1,1','nb':'4,512,16384,16384','bytes':'16384'};payload(row,b'\0'*16384)
  row['ne']='2880,32,1,1'
  with self.assertRaises(ValueError):payload(row,b'\0'*16384)
 def test_full_logit_truncation_and_same_profile_mismatch(self):
  with tempfile.TemporaryDirectory() as tmp:
   a=Path(tmp)/'a';b=Path(tmp)/'b';a.mkdir();b.mkdir()
   for name in PHASES:
    for p in (a,b):
     with (p/(name+'.logits.f32')).open('wb') as f:f.truncate(201088*4)
   compare_logits(a,b)
   (b/'decode3.logits.f32').write_bytes(b'\0')
   with self.assertRaises(ValueError):compare_logits(a,b)
 def test_invalid_native_mode_before_gguf_or_output(self):
  if not BIN.exists():self.skipTest('local compiled diagnostic unavailable')
  with tempfile.TemporaryDirectory() as tmp:
   target=Path(tmp)/'capture';r=subprocess.run([str(BIN),'/does-not-exist-model','/does-not-exist-ids',str(target),'invalid'],capture_output=True,text=True,timeout=5)
   self.assertNotEqual(r.returncode,0);self.assertIn('mode before weights',r.stderr);self.assertFalse(target.exists())
if __name__=='__main__':unittest.main()
