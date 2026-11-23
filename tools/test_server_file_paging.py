from copy import deepcopy
import unittest
from c2_server_run import server_endpoint_reasons,prospective_server_start_scope
from c2_gate import GateError
from test_c147_file_paging import paging
class ServerPaging(unittest.TestCase):
 def test_reclaim_allowed_but_oom_swap_and_limits_rejected(self):
  p,cg,_=paging();r=p['resources'];end=deepcopy(cg);end['events']['max']=5;end['memory_peak']=r['cgroup']['memory_max_bytes']+4096
  self.assertEqual(server_endpoint_reasons(end,cg,r),[])
  self.assertTrue(server_endpoint_reasons(end,cg,None))
  for bad in ('oom','oom_kill'):
   x=deepcopy(end);x['events'][bad]=1;self.assertTrue(server_endpoint_reasons(x,cg,r))
  x=deepcopy(end);x['swap_current']=1;self.assertTrue(server_endpoint_reasons(x,cg,r))
  for name in ('memory_max','memory_high','swap_max'):
   x=deepcopy(end);x[name]+=1;self.assertTrue(server_endpoint_reasons(x,cg,r))
 def test_scope_high_before_launch(self):
  p,cg,_=paging();p['execution_scope_unit']='fixed';cg['path']='/campaign/fixed.service'
  prospective_server_start_scope(p,cg,p['resources'])
  for key,value in (('path','/campaign/other.service'),('memory_high',cg['memory_high']+1)):
   x=deepcopy(cg);x[key]=value
   with self.assertRaises(GateError):prospective_server_start_scope(p,x,p['resources'])
if __name__=='__main__':unittest.main()
