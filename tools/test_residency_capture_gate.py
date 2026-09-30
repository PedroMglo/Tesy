import tempfile,unittest,csv
from pathlib import Path
from residency_capture_gate import plan,witnesses,journal_window,CORE
class CaptureTests(unittest.TestCase):
 def fixture(self,root):
  expected=[(i+1,1,'prefix-warmup',256*i,min(2043,256*i+255)) for i in range(8)]+[(9,2,'warm-prefill',2044,2048),(10,2,'warm-prefill',2049,2196)]+[(11+i,2,'decode',2197+i,2197+i) for i in range(47)]
  with (root/'calls.tsv').open('w') as f:
   f.write('call\trequest\tphase\tfirst\tlast\tn_tokens\tbegin_us\tend_us\n')
   for i,(call,req,phase,a,b) in enumerate(expected):f.write(f'{call}\t{req}\t{phase}\t{a}\t{b}\t{b-a+1}\t{100*i}\t{100*i+50}\n')
  with (root/'full-logits.f32').open('wb') as f:f.truncate(57*201088*4)
 def test_fixed_schedule_and_position_negative(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);self.fixture(p);self.assertEqual(len(plan(p)),57)
   q=p/'calls.tsv';q.write_text(q.read_text().replace('2197\t2197','2198\t2198'))
   with self.assertRaises(ValueError):plan(p)
 def test_truncated_full_logits(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);self.fixture(p)
   with (p/'full-logits.f32').open('r+b') as f:f.truncate(1)
   with self.assertRaises(ValueError):plan(p)
 def test_window_original_footer_and_ranges(self):
  from c152_journal_validate import validate
  original=Path(__file__).resolve().parents[1]/'results/c156-snapshot-gates-20260930T1000Z/native-v5-remap/journal.trace'
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'journal.trace';p.write_bytes(original.read_bytes());w=journal_window(p,{'transition_seq':0});validate(w,physical=False)
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'journal.trace';p.write_text(original.read_text().replace('#end\t29\t0','#end\t29\t1'))
   with self.assertRaises(ValueError):journal_window(p,{'transition_seq':0})
 def test_witnesses_require_active_not_only_index_names(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'witness').mkdir();rows=[]
   for c in (9,10,11,57):
    for l in range(36):
     for s in CORE:
      n=f'{c}-{l}-{s}-0.bin';(p/'witness'/n).write_bytes(b'');shape='1,4,0,1' if s=='ffn_moe_weights_softmax' else f'{4 if s=="ffn_moe_topk" else 128 if s in ("ffn_moe_logits","ffn_moe_probs") else 2880},0,1,1';rows.append(f'{n}\t0\t{shape}\n')
   (p/'witness/index.tsv').write_text(''.join(rows))
   with self.assertRaisesRegex(ValueError,'active states missing'):witnesses(p)
if __name__=='__main__':unittest.main()
