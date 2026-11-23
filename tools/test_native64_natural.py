from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import c2_server_run as server
import host_resource_policy as policy
from c2_gate import GateError
from native64_sql import grade, extract, expected, FIXTURES
from test_host_resource_policy import runtime_fixture

QUERY='''WITH ranked AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY atualizado DESC,ingest_id DESC) AS rn FROM eventos) SELECT cliente,SUM(COALESCE(valor,0)) FROM ranked WHERE rn=1 GROUP BY cliente ORDER BY cliente'''

class NaturalTests(unittest.TestCase):
    def test_sql_positive_and_discriminating_negatives(self):
        self.assertTrue(grade(QUERY)['PASS'])
        self.assertTrue(grade('```sql\n'+QUERY+'\n```')['PASS'])
        # A distinct relational formulation must not be rejected for differing text.
        alternative=('SELECT e.cliente,SUM(COALESCE(e.valor,0)) FROM eventos e '
                     'WHERE NOT EXISTS (SELECT 1 FROM eventos n WHERE n.event_id=e.event_id '
                     'AND (n.atualizado>e.atualizado OR (n.atualizado=e.atualizado AND n.ingest_id>e.ingest_id))) '
                     'GROUP BY e.cliente ORDER BY e.cliente')
        self.assertTrue(grade(alternative)['PASS'])
        for bad in ('DELETE FROM eventos',QUERY+'; SELECT 1',
                    'SELECT cliente,SUM(COALESCE(valor,0)) FROM eventos GROUP BY cliente ORDER BY cliente',
                    QUERY.replace('ingest_id DESC','ingest_id ASC'),
                    QUERY.replace('COALESCE(valor,0)','valor'),
                    'SELECT load_extension("x")','text\n```sql\n'+QUERY+'\n```',
                    'WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT sum(x) FROM c'):
            with self.subTest(query=bad),self.assertRaises(GateError):grade(bad)
        self.assertEqual(expected(FIXTURES[1]),[('ana',7),('bia',8)])

    def test_task_overrides_keep_defaults_and_reject_unfrozen_fields(self):
        cfg={'task_ids':['one','two'],'request_policy':{'max_tokens':256,'per_request_timeout_s':180}}
        self.assertEqual(server.per_task_request_policy(cfg,'one'),cfg['request_policy'])
        cfg['per_task_request_policy']={'two':{'max_tokens':384,'per_request_timeout_s':120}}
        self.assertEqual(server.per_task_request_policy(cfg,'two'),{'max_tokens':384,'per_request_timeout_s':120})
        for override in ({'three':{'max_tokens':384}},{'two':{'threads':1}},
                         {'two':{'max_tokens':True}},{'two':{'per_request_timeout_s':float('nan')}}):
            cfg['per_task_request_policy']=override
            with self.assertRaises(GateError):server.per_task_request_policy(cfg,'two')

    def entrypoint(self,late=False,parallel=False,fixed=False,outcomes=False):
        protocol,cg,sample=runtime_fixture();protocol['identity']={'model_sha256':'a'*64,'library_sha256':{'fake':'b'*64}}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'raw').mkdir();model=root/'model';model.write_bytes(b'not weights')
            pp=root/'protocol.json';pp.write_text(json.dumps(protocol))
            cg['path']=server.process_identity(os.getpid())['cgroup_path']
            cfg={'server_command':[sys.executable,'-c','import time,signal,sys; signal.signal(signal.SIGTERM,lambda *_:sys.exit(0)); time.sleep(30)'],
                'explicit_env':{},'output_root':str(root/'raw'),'backend_root':str(root),
                'task_ids':['one','two','three'],'n_ctx':8192,'total_timeout_s':10,
                'readiness_timeout_s':2,'request_policy':{'max_tokens':8,'per_request_timeout_s':2},
                'per_task_request_policy':{'two':{'max_tokens':8,'per_request_timeout_s':.05 if late else 2},
                                          'three':{'max_tokens':12,'per_request_timeout_s':2}},
                'pretokenize':True,'freeze_token_ids':True,'append_previous_assistant_to_next':True,
                'stream_requests':True,'require_natural_stop':True,'dynamic_cache_min_common':5}
            tasks=[(k,{'id':k,'category':'fixture','messages':[{'role':'user','content':k}]}) for k in cfg['task_ids']]
            if outcomes:cfg['prospective_task_outcomes']=True
            if fixed:
                cfg['append_previous_assistant_to_next']=False
                cfg['task_ids'].append('four')
                cfg['per_task_request_policy']['four']={'max_tokens':16,'per_request_timeout_s':2}
                supplied=[];fixed_tasks=[]
                for k in cfg['task_ids']:
                    supplied=supplied+[{'role':'user','content':k}]
                    fixed_tasks.append((k,{'id':k,'category':'provided-history-fixture','messages':list(supplied)}))
                    supplied=supplied+[{'role':'assistant','content':QUERY if k=='three' else '48327'}]
                tasks=fixed_tasks
            transports=[]
            def fetch(path,payload=None,timeout=None):
                if path=='/health':
                    if parallel:time.sleep(.08) # real dummy child must exec/load lib before mocked HTTP readiness
                    return {'status':'ok'}
                if path=='/v1/models':return {'data':[{'id':'fixture'}]}
                if path=='/apply-template':return {'prompt':str(len(payload['messages']))}
                if path=='/tokenize':return {'tokens':list(range({1:10,3:13,5:15,7:18}[int(payload['content'])]))}
                raise AssertionError(path)
            def stream(payload,timeout,started):
                transports.append((deepcopy(payload),timeout));time.sleep(.6)
                i=len(transports)-1;n=[10,13,15,18][i];cache=[0,10,13,15][i]
                if fixed and i==3:
                    from test_useful_latency_portfolio import QUERY as holdout_query
                else:holdout_query=''
                response={'choices':[{'message':{'role':'assistant','content':['12345','12345',QUERY,holdout_query][i]},'finish_reason':'stop'}],
                          'usage':{'prompt_tokens':n,'completion_tokens':1},
                          'timings':{'cache_n':cache,'prompt_n':n-cache}}
                if outcomes and i==0:
                    response['choices'][0]['finish_reason']='length'
                    response['usage']['completion_tokens']=8
                return response,{'done_observed':True,'first_final_content_chunk_s':.5}
            if parallel:
                from parallel_runtime import parallel_environment
                from run_bounded import sha256
                lib=Path('/lib64/libgomp.so.1').resolve()
                protocol['parallel_runtime']={'schema':'parallel-runtime-v1','environment':parallel_environment(dict(os.environ,GOMP_SPINCOUNT='0')),'libraries_sha256':{str(lib):sha256(lib)}}
                cfg['explicit_env']={'GOMP_SPINCOUNT':'0'}
                cfg['server_command'][2]='import ctypes; ctypes.CDLL("'+str(lib)+'"); '+cfg['server_command'][2]
                pp.write_text(json.dumps(protocol))
            validations=[]
            def validator(rid,item):
                validations.append(rid)
                if outcomes:
                    return {'PASS':rid!='one','outcome':'OUTPUT_CAP' if rid=='one' else 'SUCCESS'}
                if rid=='four':
                    from portfolio_workload import grade_holdout
                    return grade_holdout(item['message']['content'])
                return grade(item['message']['content']) if rid=='three' else {'PASS':True}
            ps={'VmRSS':100*2**20,'VmHWM':100*2**20,'VmSwap':0}
            thermal=deepcopy(sample['thermal']);thermal['cpu_tctl_c']=45
            with patch.object(server,'cgroup_state',return_value=cg),patch.object(server,'proc_status',return_value=ps), \
                 patch.object(server,'gpu_state',return_value=sample['gpu']),patch.object(server,'thermal_state',return_value=thermal), \
                 patch.object(server,'mem_available',return_value=22*2**30),patch.object(server,'model_fd_state',return_value={}), \
                 patch.object(policy,'host_pressure',return_value=0),patch.object(policy,'live_power',return_value=sample['resource_observation']['power']), \
                 patch.object(server,'loaded_backend_libraries',return_value={'fake':'b'*64}), \
                 patch.object(server,'fetch',side_effect=fetch),patch.object(server,'stream_chat',side_effect=stream):
                rc=server.run(SimpleNamespace(run_id='test',protocol=pp,suite='native64natural',model='target120b'),
                              protocol,cfg,tasks,model,result_validator=validator)
            raw=json.loads((root/'raw/test.json').read_text())
            if late:
                self.assertEqual(rc,1);self.assertEqual(len(transports),2)
                self.assertEqual(validations,['one']);self.assertFalse(raw['results'][-1]['accepted'])
                self.assertEqual(raw['results'][-1]['message']['content'],'12345')
                self.assertTrue(any('PER_REQUEST_WALL_TIMEOUT' in r for r in raw['stop_reasons']))
            else:
                self.assertEqual(rc,0);self.assertEqual(len(transports),4 if fixed else 3)
                self.assertEqual([r[0]['max_tokens'] for r in transports],[8,8,12,16] if fixed else [8,8,12])
                self.assertEqual([r[1] for r in transports],[2,2,2,2] if fixed else [2,2,2])
                self.assertEqual(len(transports[-1][0]['messages']),7 if fixed else 5)
                self.assertEqual(transports[-1][0]['messages'][1]['content'],'48327' if fixed else '12345')
                self.assertTrue(raw['results'][-1]['functional_validation']['PASS'])
                self.assertEqual(list(json.loads((root/'raw/test.tokenization.json').read_text())),['one','two','three','four'] if fixed else ['one','two','three'])
            if outcomes:
                self.assertTrue(raw['results'][0]['measurement_valid']);self.assertFalse(raw['results'][0]['accepted'])
                self.assertEqual(raw['results'][0]['outcome'],'OUTPUT_CAP');self.assertEqual(len(raw['results']),4)
            if parallel:self.assertEqual(raw['preflight']['actually_loaded_parallel_runtime']['initial_process_environment']['values']['GOMP_SPINCOUNT'],'0')
            self.assertIsNotNone(raw['returncode']);self.assertGreaterEqual(raw['sample_count'],1)
            self.assertFalse(Path('/proc') .joinpath(str(raw['launch_identity']['pid'])).exists())

    def test_length_kept_and_next_requests_execute_real_child(self):self.entrypoint(fixed=True,outcomes=True)

    def test_four_supplied_messages_child_entrypoint_and_holdout_prefix(self):self.entrypoint(fixed=True)
    def test_three_turn_actual_child_entrypoint(self):self.entrypoint()
    def test_parallel_runtime_actual_child_entrypoint(self):self.entrypoint(parallel=True)
    def test_late_second_preserved_and_third_never_launched(self):self.entrypoint(late=True)

if __name__=='__main__':unittest.main()
