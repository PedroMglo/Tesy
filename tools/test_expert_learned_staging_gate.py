import hashlib,json,tempfile,unittest
from pathlib import Path
import numpy as np
from expert_learned_staging_gate import affine_values

class AffineBoundary(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.weights=self.root/'weights';self.weights.mkdir();self.arm=self.root/'arm';self.arm.mkdir()
        hashes={}
        for f,n in (('weight.f32',23*128*128),('bias.f32',23*128)):
            np.zeros(n,dtype='<f4').tofile(self.weights/f);hashes[f]=hashlib.sha256((self.weights/f).read_bytes()).hexdigest()
        m={'schema':'original-score-affine-calibration-v1','status':'PASS_FIXED_TRAINING_ONLY_FIT','model_sha256':'582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d','CPU_target_layers':[2,24],'source_horizon':2,'development_used':False,'holdout_used':False,'training_BLAS_actual_threads':8,'training_conversations':[{'case':str(i),'frames':128} for i in range(8)],'training_rows_per_layer':1024,'weights_bytes':1519104,'fit_s':.1,'sha256':hashes}
        (self.weights/'manifest.json').write_text(json.dumps(m));self.meta={'learned_movement':True,'runtime_training':False,'auxiliary_root':str(self.weights),'auxiliary_sha256':hashes};self.write()
        np.ones((32,23,128),dtype='<f4').tofile(self.arm/'uncalibrated-scores.f32');np.zeros((32,23,128),dtype='<f4').tofile(self.arm/'prediction-scores.f32')
    def tearDown(self):self.temp.cleanup()
    def write(self):(self.arm/'estimator.json').write_text(json.dumps(self.meta))
    def test_reference_pass_and_wrong_output_rejected(self):
        self.assertEqual(affine_values(self.arm,self.weights,True)['status'],'PASS_INTEGRATED_AUXILIARY_AFFINE_REFERENCE')
        np.ones((32,23,128),dtype='<f4').tofile(self.arm/'prediction-scores.f32')
        with self.assertRaises(ValueError):affine_values(self.arm,self.weights,True)
    def test_auxiliary_identity_and_runtime_training_required(self):
        self.meta['runtime_training']=True;self.write()
        with self.assertRaises(ValueError):affine_values(self.arm,self.weights,True)
    def test_truncation_nonfinite_and_control_bypass(self):
        with self.assertRaises(ValueError):affine_values(self.arm,self.weights,False)
        (self.arm/'uncalibrated-scores.f32').unlink();self.assertEqual(affine_values(self.arm,self.weights,False)['status'],'PASS_AUXILIARY_LOADED_CONTROL_BYPASS')
        np.zeros(1,dtype='<f4').tofile(self.arm/'uncalibrated-scores.f32')
        with self.assertRaises(ValueError):affine_values(self.arm,self.weights,True)

if __name__=='__main__':unittest.main()
