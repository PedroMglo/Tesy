import copy,json,unittest
from c2_gate import GateError
from passive_wait_utility import *
class Utility(unittest.TestCase):
 def pair(self):
  reqs=[{'outcome':'SUCCESS','functional_success':True,'trajectory':'identical'} for _ in range(4)]
  a={'measurement_valid':True,'input_ids':[1,2],'nominal153':True,'requests':copy.deepcopy(reqs),'SQL_L':.5,'JSON_L':.5,'U':.5}
  a.update({k:10 for k in PROTECTED+('JSON_first_final_s','JSON_seconds_per_output')});b=copy.deepcopy(a);b.update(SQL_L=.4,JSON_L=.4,U=.4)
  return a,b
 def test_formula_success_failure_and_invalid(self):
  x={'outcome':'SUCCESS','functional_success':True,'validated_s':10,'completion_s':9,'validator_s':1}
  self.assertAlmostEqual(task_loss(x,120),10/122)
  for outcome in ('OUTPUT_CAP','WRONG_FINAL','DEADLINE_CENSORED'):
   x['outcome']=outcome;self.assertEqual(task_loss(x,120),1);self.assertIsNone(task_loss(x,120,valid=False))
  for bad in (float('nan'),float('inf'),0):
   x.update(outcome='SUCCESS',validated_s=bad)
   with self.assertRaises(GateError):task_loss(x,120)
  x.update(validated_s=123,completion_s=119,validator_s=1);self.assertEqual(task_loss(x,120),1)
 def test_paired_outcomes_keep_weight(self):
  x=self.pair();self.assertEqual(evaluate([x,x])['status'],'GO_S_SCREEN')
  for a,b in (x,):
   a['SQL_L']=b['SQL_L']=1;a['requests'][2].update(outcome='OUTPUT_CAP',functional_success=False);b['requests'][2].update(outcome='OUTPUT_CAP',functional_success=False)
  self.assertEqual(evaluate([x,x])['status'],'NO_GO_USEFUL_LATENCY_SCREEN')
 def test_candidate_failure_trajectory_prefix_and_missing(self):
  for what in ('candidate','trajectory','ids','invalid','missing'):
   a,b=self.pair()
   if what=='candidate':b['SQL_L']=1;b['requests'][2].update(outcome='WRONG_FINAL',functional_success=False)
   if what=='trajectory':b['requests'][2]['trajectory']='different'
   if what=='ids':b['input_ids']=[1,3]
   if what=='invalid':b['measurement_valid']=False
   if what=='missing':b['T2_first_final_s']=None
   self.assertNotIn(evaluate([(a,b),(a,b)])['status'],('GO_S_SCREEN','GO_C_CONFIRMATION'))
 def test_json_oracle_independent_cases_and_wrong_answers(self):
  self.assertEqual(JSON_EXPECTED,{'itens':[{'id':'a','valor':4},{'id':'b','valor':7},{'id':'d','valor':0}],'total':11})
  cases=[[],JSON_DATA,JSON_DATA[::-1],JSON_DATA+JSON_DATA,[{'id':'x','versao':1,'ingest':1,'cancelado':False,'valor':None}],[{'id':'x','versao':1,'ingest':1,'cancelado':True,'valor':99}]]
  expected=[{'itens':[],'total':0},JSON_EXPECTED,JSON_EXPECTED,JSON_EXPECTED,{'itens':[{'id':'x','valor':0}],'total':0},{'itens':[],'total':0}]
  for a,b in zip(cases,expected):self.assertEqual(oracle(a),b)
  self.assertTrue(grade_json(json.dumps(JSON_EXPECTED))['PASS'])
  for bad in ({'itens':[{'id':'a','valor':4},{'id':'b','valor':14},{'id':'d','valor':0}],'total':18},{'itens':[{'id':'a','valor':4},{'id':'b','valor':7},{'id':'c','valor':6},{'id':'d','valor':0}],'total':17},dict(JSON_EXPECTED,total=True)):
   with self.assertRaises(GateError):grade_json(json.dumps(bad))
 def test_deadline_censor_requires_actual_watchdog_and_terminal(self):
  raw={'stop_reasons':['PER_REQUEST_WALL_TIMEOUT','RUN_ERROR:ConnectionError:cancelled'],'returncode':-15}
  records=[{'kind':'REQUEST_START','request_id':'last','deadline_monotonic':10},{'kind':'REQUEST_TERMINAL','request_id':'last','watchdog':{'expired_monotonic':10.01,'cancel_requested_monotonic':10.01,'cancel_finished_monotonic':10.1,'cancel_error':None}}]
  self.assertEqual(terminal_censor_contract(raw,records,'last')['outcome'],'DEADLINE_CENSORED')
  for changed in ('guard','wrongtask','truncate','cancelerror','incomplete'):
   a,b=copy.deepcopy(raw),copy.deepcopy(records)
   if changed=='guard':a['stop_reasons'].append('CGROUP_PREVENTIVE_MARGIN')
   if changed=='wrongtask':b[-1]['request_id']='other'
   if changed=='truncate':b.append({'kind':'EVIDENCE_TRUNCATED','request_id':'last'})
   if changed=='cancelerror':b[-1]['watchdog']['cancel_error']='identity changed'
   if changed=='incomplete':b.pop()
   with self.assertRaises(GateError):terminal_censor_contract(a,b,'last')
if __name__=='__main__':unittest.main()
