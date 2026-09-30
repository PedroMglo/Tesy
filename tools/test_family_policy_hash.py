import unittest,tempfile,json
from pathlib import Path
from family_policy_hash import bind_start_policy
from run_bounded import sha256
from host_resource_policy import digest,derive_policy,freeze_protocol_resource_limits
from test_host_resource_policy import fixture
class PolicyHash(unittest.TestCase):
 def test_serialized_bytes_are_launch_authority(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'resource-policy.json';obj=derive_policy(snapshot=fixture());p.write_text(json.dumps(obj,indent=2)+'\n');protocol={'limits':{},'start_inventory':{},'resources':freeze_protocol_resource_limits(obj,cgroup_memory_max_bytes=18*2**30,execution_class='FILE_PAGING')}
   bind_start_policy(protocol,p);self.assertEqual(protocol['start_inventory']['policy_sha256'],sha256(p));self.assertNotEqual(sha256(p),digest(obj))
   p.write_text(json.dumps(obj));self.assertNotEqual(protocol['start_inventory']['policy_sha256'],sha256(p))
   p.write_text(json.dumps(protocol['resources']))
   with self.assertRaises(ValueError):bind_start_policy(protocol,p)
 def test_missing_blocks(self):
  with self.assertRaises(ValueError):bind_start_policy({'start_inventory':{}},'/nonexistent/policy')
if __name__=='__main__':unittest.main()
