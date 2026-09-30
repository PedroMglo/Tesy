import unittest,tempfile,json
from pathlib import Path
from family_policy_hash import bind_start_policy
from run_bounded import sha256
from host_resource_policy import digest
class PolicyHash(unittest.TestCase):
 def test_serialized_bytes_are_launch_authority(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'resource-policy.json';obj={'cap':21474836480};p.write_text(json.dumps(obj,indent=2)+'\n');protocol={'start_inventory':{}}
   bind_start_policy(protocol,p);self.assertEqual(protocol['start_inventory']['policy_sha256'],sha256(p));self.assertNotEqual(sha256(p),digest(obj))
   p.write_text(json.dumps(obj));self.assertNotEqual(protocol['start_inventory']['policy_sha256'],sha256(p))
 def test_missing_blocks(self):
  with self.assertRaises(ValueError):bind_start_policy({'start_inventory':{}},'/nonexistent/policy')
if __name__=='__main__':unittest.main()
