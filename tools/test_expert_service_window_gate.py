import copy,tempfile,unittest
from pathlib import Path
from expert_service_window_gate import events,FIELDS
class Window(unittest.TestCase):
 def rows(self):
  rows=[]
  def add(k,t,c,l=-1,e=-1,state=0):
   rows.append(dict(zip(FIELDS,(k,t,c,1,l,e,e if e>=0 else -1,1 if e>=0 else 0,-1,state,1))))
  for c in range(33):
   t=10000+c*10000;add(15,t,c)
   if c:
    for l in range(36):
     if l<25:add(1,t+l*100+1,c,l)
     add(2,t+l*100+2,c,l)
     for e in range(4):add(3,t+l*100+3,c,l,e,2)
   add(16,t+9000,c)
  return rows
 def check(self,rows,on=True):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'events';p.write_text(' '.join(FIELDS)+'\n'+''.join(' '.join(str(x[k]) for k in FIELDS)+'\n' for x in rows));return events(p,on)
 def test_complete(self):self.check(self.rows());self.check([],False)
 def test_missing_duplicate_future_feature(self):
  r=self.rows();i=next(i for i,x in enumerate(r) if x['kind']==1)
  for mutated in (r[:i]+r[i+1:],r+[r[i]],copy.deepcopy(r)):
   if len(mutated)==len(r):mutated[i]['us']=999999999
   with self.assertRaises(ValueError):self.check(mutated)
 def test_missing_demand_and_bad_state(self):
  r=self.rows();i=next(i for i,x in enumerate(r) if x['kind']==3)
  with self.assertRaises(ValueError):self.check(r[:i]+r[i+1:])
  r[i]['bytes']=9
  with self.assertRaises(ValueError):self.check(r)
 def test_off_and_missing_router(self):
  r=self.rows()
  with self.assertRaises(ValueError):self.check(r,False)
  with self.assertRaises(ValueError):self.check([x for x in r if x['kind']!=2])
if __name__=='__main__':unittest.main()
