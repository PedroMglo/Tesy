import unittest,copy
from pathlib import Path
from c152_snapshot_read import snapshot,routes
from c152_journal_validate import validate
from residency_counterfactual import simulate,credit
ROOT=Path(__file__).resolve().parents[1]/'results/c156-snapshot-gates-20260930T1000Z/native-v5-remap'
class ConditionalFixedRouting(unittest.TestCase):
 def test_native_baseline_decisions_and_final_hotness_mapping(self):
  a=snapshot(ROOT/'before.snap',physical=False);b=snapshot(ROOT/'after.snap',physical=False);r=routes(ROOT/'routes.bin');out,s=simulate(a,r,4,4);self.assertEqual(out[0]['misses'],[4,5]);self.assertEqual(out[0]['victims'],[2,3])
  for k in ('slot_expert','slot_state','slot_gen','slot_last_use','expert_slot','route_hotness','use_counter'):self.assertEqual(s['layers'][0][k],b['layers'][0][k])
 def test_loading_seed_rejected_not_drained(self):
  a=snapshot(ROOT/'before.snap',physical=False);a['layers'][0]['slot_state'][0]=1
  with self.assertRaises(ValueError):simulate(a,routes(ROOT/'routes.bin'),4,4)
 def test_same_misses_get_zero_credit_and_wake_tail_preserved(self):
  initial={'call_id':1};b={'begin':{'call_id':2,'layer':0,'mono_us':10},'end':{'mono_us':110},'blocking_commits':[{'expert':1,'mono_us':40},{'expert':2,'mono_us':100}]};j={'barriers':[b]}
  r=credit(j,initial,[{'call_id':2,'layer':0,'misses':[1,2]}]);self.assertEqual(r['conditional_avoided_wait_union_s'],0)
  r=credit(j,initial,[{'call_id':2,'layer':0,'misses':[1]}]);self.assertEqual(r['conditional_avoided_wait_union_s'],60/1e6)
  r=credit(j,initial,[{'call_id':2,'layer':0,'misses':[]}]);self.assertEqual(r['conditional_avoided_wait_union_s'],100/1e6)
if __name__=='__main__':unittest.main()
