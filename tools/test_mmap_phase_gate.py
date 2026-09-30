import tempfile,unittest,json,subprocess,struct
from pathlib import Path
from mmap_phase_gate import PHASES,payload,compare_logits,logits,inspect,reference_result
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
 def test_reference_rows_and_bitwise_flags_are_required(self):
  import copy
  result={'schema':'c149-upstream-cpu-expert-layer-reference-v1','layer':3,'device':'cpu','canonical_layer_bytes':1697956352,'all_bitwise':True,'numeric_rows':5,'masked_rows':0,'rows':[]}
  for phase in PHASES:
   row={'phase':phase,'state':'NUMERIC','tokens':32 if phase=='prefill0' else 1,'routing_ids_equal':True,'routing_weights_bitwise':True,'ffn_bitwise':True}
   row.update({key:0 for key in ('routing_weights_max_abs','routing_weights_rmse','routing_weights_nonfinite','ffn_max_abs','ffn_rmse','ffn_nonfinite')});result['rows'].append(row)
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'out';p.write_text(json.dumps(result)+'\n');reference_result(p,3)
   for mutation in ('missing','tokens','layer','bits','finite','duplicate'):
    bad=copy.deepcopy(result)
    if mutation=='missing':bad['rows'].pop()
    if mutation=='tokens':bad['rows'][1]['tokens']=32
    if mutation=='layer':bad['layer']=4
    if mutation=='bits':bad['rows'][2]['routing_weights_bitwise']=False
    if mutation=='finite':bad['rows'][2]['ffn_rmse']=float('nan')
    p.write_text(json.dumps(bad)+'\n'+(json.dumps(bad)+'\n' if mutation=='duplicate' else ''))
    with self.subTest(mutation=mutation),self.assertRaises(ValueError):reference_result(p,3)
 def test_invalid_native_mode_before_gguf_or_output(self):
  if not BIN.exists():self.skipTest('local compiled diagnostic unavailable')
  with tempfile.TemporaryDirectory() as tmp:
   target=Path(tmp)/'capture';r=subprocess.run([str(BIN),'/does-not-exist-model','/does-not-exist-ids',str(target),'invalid'],capture_output=True,text=True,timeout=5)
   self.assertNotEqual(r.returncode,0);self.assertIn('mode before weights',r.stderr);self.assertFalse(target.exists())
if __name__=='__main__':unittest.main()
