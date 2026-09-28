"""Exercise the real runner with a child process and mocked model/sensors."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import c2_server_run as runner
import host_resource_policy
from c9_server_admission import validate_receipt
from c2_gate import GateError, strict_json
from host_resource_policy import GIB
from test_host_resource_policy import runtime_fixture


class ProspectiveRunnerEntryPoint(unittest.TestCase):
    def test_child_launch_monitor_receipt_and_negative_controls(self):
        protocol,cgroup,sample=runtime_fixture()
        protocol.update(identity={'model_sha256':'a'*64,
                                  'library_sha256':{'libfake.so':'b'*64}})
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);rawroot=root/'raw';rawroot.mkdir()
            model=root/'tiny-model';model.write_bytes(b'model-free')
            protocol_path=root/'protocol.json'
            protocol_path.write_text(json.dumps(protocol,allow_nan=False))
            child_code=('import signal,time,sys\n'
                        'signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))\n'
                        'while True:time.sleep(.1)\n')
            config={'server_command':[sys.executable,'-c',child_code],
                    'explicit_env':{},'request_policy':{'max_tokens':8,
                    'per_request_timeout_s':10},'total_timeout_s':15,
                    'output_root':str(rawroot),'backend_root':str(root),
                    'stream_requests':False}
            args=SimpleNamespace(run_id='c55-entry',protocol=protocol_path,
                                 suite='c55mock',model='target120b')
            task={'id':'mock-1','category':'model-free','prompt':'hello'}
            cgroup['path']=runner.process_identity(__import__('os').getpid())['cgroup_path']
            def fetch(path,payload=None,timeout=None):
                if path=='/health':return {'status':'ok'}
                if path=='/v1/models':return {'data':[{'id':'mock-model'}]}
                if path=='/v1/chat/completions':
                    time.sleep(2.2)  # produce real monitor samples and endpoint coverage
                    return {'choices':[{'message':{'role':'assistant','content':'ok'},
                                        'finish_reason':'stop'}],
                            'usage':{'prompt_tokens':1,'completion_tokens':1}}
                raise AssertionError(path)
            ps={'VmRSS':100*2**20,'VmHWM':100*2**20,'VmSwap':0}
            gpu=deepcopy(sample['gpu']);thermal=deepcopy(sample['thermal'])
            start_thermal=deepcopy(thermal);start_thermal['cpu_tctl_c']=45
            thermal_calls=[0]
            def thermal_read(*,prospective):
                thermal_calls[0]+=1
                return start_thermal if thermal_calls[0]==1 else thermal
            with patch.object(runner,'cgroup_state',return_value=cgroup), \
                 patch.object(runner,'proc_status',return_value=ps), \
                 patch.object(runner,'gpu_state',return_value=gpu), \
                 patch.object(runner,'thermal_state',side_effect=thermal_read), \
                 patch.object(runner,'mem_available',return_value=22*GIB), \
                 patch.object(runner,'model_fd_state',return_value={}), \
                 patch.object(host_resource_policy,'host_pressure',return_value=0), \
                 patch.object(host_resource_policy,'live_power',return_value=sample['resource_observation']['power']), \
                 patch.object(runner,'loaded_backend_libraries',return_value={'libfake.so':'b'*64}), \
                 patch.object(runner,'fetch',side_effect=fetch):
                self.assertEqual(runner.run(args,protocol,config,[('mock-1',task)],model),0)
            result=strict_json((rawroot/'c55-entry.json').read_text())
            samples=[strict_json(line) for line in
                     (rawroot/'c55-entry.samples.jsonl').read_text().splitlines()]
            self.assertEqual(len(result['results']),1)
            self.assertGreaterEqual(len(samples),2)
            self.assertEqual(result['preflight']['actually_loaded_backend_libraries_sha256'],
                             {'libfake.so':'b'*64})
            self.assertIsNotNone(validate_receipt(protocol,config,result,samples,root,
                               run_id='c55-entry',expected_results=1))
            def bad(mutator):
                copy=deepcopy(samples);mutator(copy)
                with self.assertRaises(GateError):
                    validate_receipt(protocol,config,result,copy,root,
                                     run_id='c55-entry',expected_results=1)
            bad(lambda x:x[0]['thermal'].update(cpu_tctl_c=100))
            bad(lambda x:x[0]['cgroup'].update(memory_max=17*GIB))
            bad(lambda x:x[0]['gpu'].update(uuid='GPU-bad'))
            bad(lambda x:x[0]['resource_observation'].update(host_psi_full_avg10=float('inf')))
            broken=deepcopy(result)
            broken['preflight']['actually_loaded_backend_libraries_sha256']={}
            with self.assertRaises(GateError):
                validate_receipt(protocol,config,broken,samples,root,
                                 run_id='c55-entry',expected_results=1)


if __name__=='__main__':unittest.main()
