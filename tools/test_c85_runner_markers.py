"""Exercise opt-in request markers through the real bounded runner, model-free."""

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
from c2_gate import GateError, strict_json
from c85_request_markers import validate
from host_resource_policy import GIB
from test_host_resource_policy import runtime_fixture


class MarkerEntryPointTest(unittest.TestCase):
    def test_one_complete_request_and_missing_contract(self):
        protocol,cgroup,sample=runtime_fixture()
        protocol.update(identity={'model_sha256':'a'*64,
                                  'library_sha256':{'libfake.so':'b'*64}},
                        trace={'request_marker_schema':'c85-request-monotonic-v1'})
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); rawroot=root/'raw';rawroot.mkdir()
            model=root/'tiny-model';model.write_bytes(b'model-free')
            protocol_path=root/'protocol.json'
            protocol_path.write_text(json.dumps(protocol,allow_nan=False))
            child=('import signal,time,sys\n'
                   'signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))\n'
                   'while True:time.sleep(.1)\n')
            config={'server_command':[sys.executable,'-c',child],
                    'explicit_env':{},'request_policy':{'max_tokens':8,
                    'per_request_timeout_s':10},'total_timeout_s':15,
                    'output_root':str(rawroot),'backend_root':str(root),
                    'stream_requests':False,
                    'record_monotonic_request_markers':True}
            args=SimpleNamespace(run_id='c85-entry',protocol=protocol_path,
                                 suite='c85mock',model='target120b')
            task={'id':'one','category':'model-free','prompt':'hello'}
            cgroup['path']=runner.process_identity(__import__('os').getpid())['cgroup_path']
            def fetch(path,payload=None,timeout=None):
                if path=='/health':return {'status':'ok'}
                if path=='/v1/models':return {'data':[{'id':'mock-model'}]}
                if path=='/v1/chat/completions':
                    time.sleep(2.2)
                    return {'choices':[{'message':{'role':'assistant','content':'ok'},
                                        'finish_reason':'stop'}],
                            'usage':{'prompt_tokens':1,'completion_tokens':1}}
                raise AssertionError(path)
            ps={'VmRSS':100*2**20,'VmHWM':100*2**20,'VmSwap':0}
            gpu=deepcopy(sample['gpu']); thermal=deepcopy(sample['thermal'])
            start_thermal=deepcopy(thermal);start_thermal['cpu_tctl_c']=45
            calls=[0]
            def thermal_read(*,prospective):
                calls[0]+=1
                return start_thermal if calls[0]==1 else thermal
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
                self.assertEqual(runner.run(args,protocol,config,[('one',task)],model),0)
            result=strict_json((rawroot/'c85-entry.json').read_text())
            markers=rawroot/'c85-entry.request-markers.jsonl'
            self.assertEqual(validate(markers,'c85-entry',['one'],result['results'])['status'],'PASS')
            self.assertIn('CLOCK_MONOTONIC',result['preflight']['trace_clock'])
            self.assertEqual(len((rawroot/'c85-entry.samples.jsonl').read_text().splitlines()) >= 2,True)
            broken=deepcopy(protocol);broken.pop('trace')
            with self.assertRaises(GateError):
                runner.run(args,broken,config,[('one',task)],model)
            malformed=dict(config,record_monotonic_request_markers=1)
            with self.assertRaises(GateError):
                runner.run(args,protocol,malformed,[('one',task)],model)


if __name__=='__main__':unittest.main()
