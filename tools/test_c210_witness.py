import copy,unittest
from c210_witness_gate import validate_rows,FIELDS,SELECTED
from c2_gate import GateError
class Witness(unittest.TestCase):
 def fixture(self):
  expected={(p,l,0,30,2) for p,l in SELECTED};rows=[]
  for phase,layer,wave,logical,slot in sorted(expected):
   for k in range(6):rows.append(dict(zip(FIELDS,[phase,str(layer),str(wave),str(logical),str(slot),'1',str(k),str(4406400 if k<3 else 11520),'EQUAL'])))
  return rows,expected
 def test_full(self):
  r,e=self.fixture();self.assertEqual(validate_rows(r,e)['components'],42)
 def test_negatives(self):
  r,e=self.fixture()
  variants=[r[:-1],r+[r[0]], [x for x in r if x['phase']!='decode0']]
  for field,value in [('generation','0'),('logical','129'),('bytes','11520'),('tensor','9'),('status','STALE'),('slot','41')]:
   v=copy.deepcopy(r);v[0][field]=value;variants.append(v)
  for v in variants:
   with self.subTest(v=v[:1]),self.assertRaises(GateError):validate_rows(v,e)
if __name__=='__main__':unittest.main()
