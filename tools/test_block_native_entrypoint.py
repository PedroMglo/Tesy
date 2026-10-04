import json
from pathlib import Path
import subprocess
import tempfile
import unittest


class NativeAdmissionBeforeWeights(unittest.TestCase):
    binary=Path(__file__).resolve().parents[1]/'results/c236-post-c235-blocks-expert-reuse-20261004T105527Z/build/block-native'

    def test_bad_inputs_mode_shape_and_replaced_root_are_premodel(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);fixture=d/'fixture.json';out=d/'output'
            for ids,mode,count,message in [([], 'generate',128,'input/context reserve'),
                    ([-1], 'generate',128,'invalid official input'),
                    ([1], 'unknown',128,'unknown native mode'),
                    ([1], 'block',64,'unfrozen count/block')]:
                fixture.write_text(json.dumps({'case':{'ids':ids}}))
                result=subprocess.run([str(self.binary),'DO_NOT_OPEN_MODEL',str(fixture),'case',str(out),mode,str(count),'v1'],text=True,capture_output=True,timeout=5)
                self.assertEqual(result.returncode,1)
                self.assertIn(message,result.stderr)
                self.assertNotIn('C80_CONTEXT_READY',result.stdout)
                self.assertFalse(out.exists())
            fixture.write_text(json.dumps({'case':{'ids':[1]}}));out.mkdir()
            result=subprocess.run([str(self.binary),'DO_NOT_OPEN_MODEL',str(fixture),'case',str(out),'generate','128','v1'],text=True,capture_output=True,timeout=5)
            self.assertEqual(result.returncode,1);self.assertIn('output root reused',result.stderr)


if __name__=='__main__': unittest.main()
