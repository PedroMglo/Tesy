import copy,unittest
from pathlib import Path
from c152_snapshot_read import snapshot,routes
from c152_journal_validate import validate
from residency_primary_replay import replay,ReplayMismatch
ROOT=Path(__file__).resolve().parents[1]/'results/c156-snapshot-gates-20260930T1000Z/native-v5-remap'
class IndependentPrimaryPolicy(unittest.TestCase):
 def data(self):
  return snapshot(ROOT/'before.snap',physical=False),snapshot(ROOT/'after.snap',physical=False),validate(ROOT/'journal.trace',physical=False)['rows'],routes(ROOT/'routes.bin')
 def test_real_source_fixture_not_journal_driven_victim(self):
  a,b,j,r=self.data();out=replay(a,b,j,r);self.assertEqual(out['status'],'LOGICAL_REPLAY_MATCHED');self.assertEqual(out['statistics']['generated_victims'],2);self.assertEqual(out['statistics']['demands'],4)
 def test_first_divergence_for_causal_fields(self):
  for field in ('victim','hotness','routing','counter','commit'):
   with self.subTest(field=field):
    a,b,j,r=self.data()
    if field=='victim':
     e=next(e for e in j if e['kind']=='EVICT');e['slot']=(e['slot']+1)%4
    elif field=='hotness':a['layers'][0]['route_hotness'][2]=2**32-1
    elif field=='routing':r[0]['ids']=[6 if x==4 else x for x in r[0]['ids']]
    elif field=='counter':a['n_calls']+=1
    elif field=='commit':next(e for e in j if e['kind']=='RESIDENT_COMMIT')['generation']+=1
    with self.assertRaises(ReplayMismatch):replay(a,b,j,r)
 def test_state_fields_final_not_only_load_totals(self):
  a,b,j,r=self.data();b['layers'][0]['route_hotness'][0]+=1;out=replay(a,b,j,r);self.assertEqual(out['status'],'REPLAY_STATE_MISMATCH');self.assertEqual(out['differences'][0]['field'],'route_hotness')
 def test_wave_not_silently_treated_as_remap(self):
  a,b,j,r=self.data();r[0]['mode']=1
  with self.assertRaisesRegex(ReplayMismatch,'WAVE_SCOPE_UNQUALIFIED'):replay(a,b,j,r)
if __name__=='__main__':unittest.main()
