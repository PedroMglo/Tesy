import subprocess
import unittest
from pathlib import Path

class NativeHeadBoundary(unittest.TestCase):
    def test_actual_native_stale_tail_counterproof_without_weights(self):
        root=Path(__file__).resolve().parents[1]
        exe=root/'results/c236-post-c235-blocks-expert-reuse-20261004T105527Z/build/block-eagle3-probe-kv-repair'
        r=subprocess.run([str(exe),'--self-test'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('PASS_MODEL_FREE_HEAD_KV_BOUNDARY',r.stdout)
        self.assertIn('"weights_loaded":false',r.stdout)

if __name__=='__main__':unittest.main()
