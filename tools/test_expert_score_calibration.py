import unittest
import numpy as np
from expert_score_calibration import fit,predict

class Calibration(unittest.TestCase):
 def test_identity_reference(self):
  x=np.array([[1,2,3],[3,1,0],[2,0,1],[4,2,0]],dtype=float);w,b=fit(x,x)
  np.testing.assert_array_equal(w,np.eye(3));np.testing.assert_array_equal(b,np.zeros(3));np.testing.assert_array_equal(predict(x,w,b),x)
 def test_constant_bias_independent_gold(self):
  x=np.ones((4,3));y=x+np.array([0,2,-1]);w,b=fit(x,y)
  np.testing.assert_array_equal(w,np.eye(3));np.testing.assert_array_equal(b,[0,2,-1]);self.assertEqual(np.argmax(predict(np.ones((1,3)),w,b)),1)
 def test_missing_nonfinite_or_unpaired_rejected(self):
  for x,y in [(np.empty((0,3)),np.empty((0,3))),(np.ones((1,3)),np.ones((1,3))),(np.ones((3,2)),np.ones((3,3))),(np.array([[1,float('nan')],[2,3]]),np.ones((2,2))),(np.ones((2,2)),np.full((2,2),float('inf')))]:
   with self.assertRaises(ValueError):fit(x,y)
 def test_wrong_model_shape_rejected(self):
  with self.assertRaises(ValueError):predict(np.ones((2,3)),np.eye(2),np.zeros(2))
if __name__=='__main__':unittest.main()
