"""Real model-free children prove selective exec environment and actual mappings."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

from c2_gate import GateError
from parallel_runtime import parallel_environment, validate_launch_runtime, mapped_parallel_runtime
from run_bounded import sha256


class ParallelExec(unittest.TestCase):
    def test_unset_and_value_are_distinct_in_real_children(self):
        lib=Path('/lib64/libgomp.so.1').resolve()
        for value in (None,'0'):
            env={k:v for k,v in os.environ.items() if not k.startswith(('OMP_','GOMP_','KMP_'))}
            if value is not None:env['GOMP_SPINCOUNT']=value
            contract={'schema':'parallel-runtime-v1','environment':parallel_environment(env),
                      'libraries_sha256':{str(lib):sha256(lib)}}
            validate_launch_runtime(contract,env)
            code='import ctypes,time; ctypes.CDLL('+repr(str(lib))+'); print("ready",flush=True); time.sleep(5)'
            child=subprocess.Popen([sys.executable,'-c',code],env=env,stdout=subprocess.PIPE,text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(),'ready')
                actual=mapped_parallel_runtime(child.pid,contract)
                self.assertEqual(actual['initial_process_environment'],contract['environment'])
                wrong=dict(env)
                if value is None:wrong['GOMP_SPINCOUNT']='0'
                else:wrong.pop('GOMP_SPINCOUNT')
                with self.assertRaises(GateError):validate_launch_runtime(contract,wrong)
                corrupted=dict(contract,libraries_sha256={str(lib):'0'*64})
                with self.assertRaises(GateError):validate_launch_runtime(corrupted,env)
            finally:
                child.terminate();child.wait(timeout=2);child.stdout.close()


if __name__=='__main__':unittest.main()
