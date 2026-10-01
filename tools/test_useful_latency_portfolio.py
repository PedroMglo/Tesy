import copy,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from c2_gate import GateError
from useful_latency_evaluate import evaluate,PROTECTED
from portfolio_workload import grade_holdout,HOLDOUT_FIXTURES
from parallel_runtime import parallel_environment,validate_launch_runtime
from useful_latency_portfolio import supplied_workload,checker
from test_native64_root_entrypoint import RootEntrypoint

QUERY="""WITH r AS (SELECT pedido_id,SUM(COALESCE(valor,0)) AS total FROM reembolsos GROUP BY pedido_id), p AS (SELECT p.cliente_id,SUM(COALESCE(p.valor,0)-COALESCE(r.total,0)) AS total FROM pedidos p LEFT JOIN r ON r.pedido_id=p.pedido_id WHERE p.estado='ok' GROUP BY p.cliente_id) SELECT c.cliente_id,c.nome,COALESCE(p.total,0) FROM clientes c LEFT JOIN p ON p.cliente_id=c.cliente_id ORDER BY c.cliente_id"""
class Portfolio(unittest.TestCase):
 def pair(self):
  a={'profile':'A','valid':True,'input_ids':[1,2],'trajectory':'same'}
  a.update({k:10 for k in ('SQL_validated_s',)+PROTECTED})
  b=dict(a,profile='B');b['SQL_validated_s']=9
  return a,b
 def test_gate_and_paired_formula(self):
  p=self.pair();self.assertEqual(evaluate([p,p],'H1')['status'],'GO_SCREEN')
  p[1]['SQL_validated_s']=11;self.assertEqual(evaluate([p,p],'H1')['status'],'NO_GO_SCREEN')
 def test_individual_regression_not_hidden_by_median(self):
  x,y=self.pair(),self.pair();x[1]['cold_prefill_s']=12;y[1]['cold_prefill_s']=7
  self.assertEqual(evaluate([x,y],'H1')['status'],'NO_GO_SCREEN')
 def test_output_difference_h1_allowed_h2_rejected(self):
  p=self.pair();p[1]['trajectory']='more reasoning'
  self.assertEqual(evaluate([p,p],'H1')['status'],'GO_SCREEN')
  self.assertEqual(evaluate([p,p],'H2')['status'],'FAIL_SAME_PROFILE_OBSERVABLE_TRAJECTORY')
 def test_invalid_fast_output_not_gain(self):
  p=self.pair();p[1]['valid']=False;p[1]['SQL_validated_s']=.1
  self.assertEqual(evaluate([p,p],'H1')['status'],'FAIL_OR_INCOMPLETE_EVIDENCE')
 def test_wrong_input_rejected(self):
  p=self.pair();p[1]['input_ids']=[1,3]
  self.assertEqual(evaluate([p,p],'H1')['status'],'INCONCLUSIVE_INPUT_OR_PREFIX')
 def test_holdout_six_fixtures_and_negatives(self):
  self.assertEqual(len(HOLDOUT_FIXTURES),6);self.assertTrue(grade_holdout(QUERY)['PASS'])
  for bad in (QUERY.replace("p.estado='ok'","1=1"),QUERY.replace('LEFT JOIN p','JOIN p'),QUERY.replace('SUM(COALESCE(valor,0))','MAX(COALESCE(valor,0))'),QUERY+'; SELECT 1','DELETE FROM pedidos','SELECT load_extension(\'x\')'):
   with self.subTest(bad=bad),self.assertRaises(GateError):grade_holdout(bad)
 def test_supplied_transcript_and_anchor(self):
  w=supplied_workload();self.assertEqual([len(w['official_ids'][k]) for k,_ in w['tasks']],[2043,2197,2292])
  self.assertEqual(w['tasks'][1][1]['messages'][1]['content'].strip(),'48327')
  self.assertEqual(w['tasks'][2][1]['messages'][3]['content'].strip(),'48327')
 def test_new_t1_not_used_for_fixed_t2(self):
  c=checker();self.assertTrue(c('c112-code',{'message':{'content':'12345'}})['PASS'])
  self.assertTrue(c('c112-repeat',{'message':{'content':'48327'}})['PASS'])
  with self.assertRaises(ValueError):c('c112-repeat',{'message':{'content':'12345'}})
 def test_selective_environment_unset_not_zero(self):
  self.assertNotEqual(parallel_environment({}),parallel_environment({'GOMP_SPINCOUNT':'0'}))
  self.assertNotIn('SECRET',parallel_environment({'SECRET':'hidden'})['values'])
  with self.assertRaises(GateError):validate_launch_runtime({'schema':'parallel-runtime-v1','environment':parallel_environment({}),'libraries_sha256':{}},{'GOMP_SPINCOUNT':'0'})

if __name__=='__main__':unittest.main()
