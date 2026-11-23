"""Exercise the real sample validator; no simulated resource monitor success."""
import json
import unittest
from pathlib import Path
from c118_start_inventory import validate_sample
from host_resource_policy import derive_policy,freeze_protocol_resource_limits

class PolicySchema(unittest.TestCase):
    def test_producer_inventory_policy_and_runtime_guards_are_distinct(self):
        root=Path(__file__).resolve().parents[1]
        d=root/'results/c252-head-conversion-inventory-schema-20261004'
        p=json.loads((d/'protocol.json').read_text());policy=json.loads((d/'resource-policy.json').read_text())
        self.assertEqual(policy,derive_policy(snapshot=json.loads((d/'snapshot.json').read_text())))
        self.assertEqual(p['resources'],freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=4*1024**3))
        obs=json.loads((root/'results/c247-b8-complete-output-amortization-20261004/raw/c247-development-code-rle-1.start-inventory.jsonl').read_text().splitlines()[0])['observation']
        power={k:policy['power'][k] for k in ('source','profile')}
        with self.assertRaises(KeyError):validate_sample(obs,policy=p['resources'],cap_bytes=4*1024**3,expected_power=power)
        validate_sample(obs,policy=policy,cap_bytes=4*1024**3,expected_power=power)

if __name__=='__main__':unittest.main()
