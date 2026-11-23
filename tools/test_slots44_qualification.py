import copy,unittest
from unittest.mock import patch
from pathlib import Path
import slots44_qualification as q
from c2_gate import GateError
from passive_wait_utility import task_loss,terminal_censor_contract,evaluate as historical_h2
from native64_numeric import read
import c143_slots40_optin as launcher
class Contract(unittest.TestCase):
 def fixture(self):
  source=read(Path('results/c222-passive-wait-screen-20261001/c222-1-A-receipt.json'))['row']
  ids=copy.deepcopy(source['input_ids']);ids[q.JSON_ID]=[10,11,12]
  pairs=[];order=[]
  for j,sequence in enumerate(('AB','BA','AB')):
   rows={}
   for profile in sequence:
    n=len(order)+1;rid=f'test-{n}-{profile}';order.append((rid,profile));r=copy.deepcopy(source)
    r.update(profile=profile,run_id=rid,slots=40 if profile=='A' else 44,ubatch=32,input_ids=ids)
    req=copy.deepcopy(r['requests'][2]);req['id']=q.JSON_ID;req['native_timings']['cache_n']=0;req['native_timings']['prompt_n']=3;r['requests'].append(req)
    for i,req in enumerate(r['requests']):
     scale=.8 if profile=='B' else 1
     for k in ('validated_s','completion_s','first_final_s'):req[k]*=scale
     t=req['native_timings'];t['prompt_ms']*=scale;t['predicted_ms']*=scale
     req['L']=task_loss(req,q.DEADLINES[i]);tag=('cold','T2','SQL','JSON')[i]
     for k in ('first_final_s','completion_s'):r[tag+'_'+k]=req[k]
     r[tag+'_seconds_per_output']=t['predicted_ms']/1000/t['predicted_n']
     if i==0:r['cold_prefill_s']=t['prompt_ms']/1000
     if i==1:r['incremental_prefill_s']=t['prompt_ms']/1000
    r['SQL_L']=r['requests'][2]['L'];r['JSON_L']=r['requests'][3]['L'];r['U']=(r['SQL_L']+r['JSON_L'])/2
    rows[profile]=r
   pairs.append((rows['A'],rows['B']))
  return pairs,ids,order
 def test_exact_population_accepts_distinct_valid_text(self):
  p,ids,o=self.fixture();p[0][1]['requests'][2]['trajectory']['message']['content']='different correct SELECT'
  self.assertEqual(q.evaluate(p,ids,o)['status'],'GO_CONFIRMATION')
 def test_empty_missing_duplicate_reordered_profiles_ids_finite_scalar(self):
  for bad in ('empty','missing','duplicate','order','profile','slots','input','nan','scalar','pair','runid'):
   p,ids,o=self.fixture();r=p[0][1]
   if bad=='empty':r['requests']=[]
   if bad=='missing':r['requests'].pop()
   if bad=='duplicate':r['requests'][3]['id']=r['requests'][2]['id']
   if bad=='order':r['requests'].reverse()
   if bad=='profile':r['profile']='A'
   if bad=='slots':r['slots']=48
   if bad=='input':r['input_ids']=dict(ids,**{q.JSON_ID:[]})
   if bad=='nan':r['requests'][2]['validated_s']=float('nan')
   if bad=='scalar':r['SQL_L']=.01
   if bad=='pair':p.pop()
   if bad=='runid':r['run_id']='other'
   self.assertNotEqual(q.evaluate(p,ids,o)['status'],'GO_CONFIRMATION',bad)
 def test_functional_failures_never_deliver(self):
  for sides in ((0,),(1,),(0,1)):
   p,ids,o=self.fixture()
   for side in sides:
    r=p[0][side];req=r['requests'][2];req.update(outcome='OUTPUT_CAP',functional_success=False,L=1.);r['SQL_L']=1;r['U']=(1+r['JSON_L'])/2
   self.assertEqual(q.evaluate(p,ids,o)['status'],'NO_GO_NEW_SLOTS44_UTILITY_QUALIFICATION')
   self.assertIn('FUNCTIONAL_FAILURE',q.futility(*p[0],ids))
 def test_early_pair_nonpositive_or_protection_stops(self):
  p,ids,_=self.fixture();p[0]=(p[0][0],copy.deepcopy(p[0][0]));p[0][1].update(profile='B',slots=44)
  self.assertIn('PRIMARY_NONPOSITIVE',q.futility(*p[0],ids))
 def test_old_H2_trajectory_rule_preserved(self):
  p,ids,o=self.fixture();p[0][1]['requests'][2]['trajectory']['message']['content']='different'
  self.assertEqual(historical_h2(p[:2])['status'],'FAIL_SAME_PROFILE_OBSERVABLE_TRAJECTORY')
 def test_deadline_never_resource_censure(self):
  raw={'stop_reasons':['PER_REQUEST_WALL_TIMEOUT'],'returncode':-15};e=[{'kind':'REQUEST_START','request_id':'last','deadline_monotonic':10},{'kind':'REQUEST_TERMINAL','request_id':'last','watchdog':{'expired_monotonic':10,'cancel_requested_monotonic':10.01,'cancel_finished_monotonic':10.1,'cancel_error':None}}]
  self.assertEqual(terminal_censor_contract(raw,e,'last')['outcome'],'DEADLINE_CENSORED')
  raw['stop_reasons'].append('CGROUP_PREVENTIVE_MARGIN')
  with self.assertRaises(GateError):terminal_censor_contract(raw,e,'last')
 def test_explicit44_cap_and_original_defaults(self):
  try:
   for cap in (None,17*2**30,20*2**30+1):
    with self.assertRaises(GateError):launcher.select_profile('slots44',cap)
   launcher.select_profile('slots44',19*2**30);self.assertEqual(launcher.CAP,19*2**30)
   self.assertEqual(launcher.CONFIG_NAME,'c142-p1-candidate')
   launcher.select_profile('slots40');self.assertEqual(launcher.CAP,18*2**30)
  finally:launcher.select_profile('slots40')
 def test44_preset_contains_actual_slots_cap_and_unset_spin(self):
  import tempfile,shutil,json,os
  from types import SimpleNamespace
  try:
   launcher.select_profile('slots44',20*2**30)
   p,c,stat=launcher.identity()
   def inv(dst):
    for name in ('snapshot.json','resource-policy.json'):shutil.copy2('results/c226-post-c225-slots44-20261001T155427Z/'+name,dst/name)
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)/'preset'
    with patch.object(launcher,'identity',return_value=(p,c,stat)),patch.object(launcher,'no_other_model'),patch.object(launcher.c55_inventory,'run',inv),patch.object(launcher.os,'statvfs',return_value=SimpleNamespace(f_bavail=50*2**30,f_frsize=1)),patch.dict(os.environ,{},clear=True):
     launcher.prepare(root,18449,520)
     preset=read(root/'preset.json');self.assertEqual(preset['cap_bytes'],20*2**30)
     cmd=preset['server_command'];self.assertEqual(cmd[cmd.index('--moe-stream-cache')+1],'44s')
     self.assertNotIn('GOMP_SPINCOUNT',preset['parallel_environment']['values'])
     self.assertEqual(read(root/'resource-protocol.json')['resources']['cgroup']['memory_max_bytes'],20*2**30)
  finally:launcher.select_profile('slots40')
if __name__=='__main__':unittest.main()
