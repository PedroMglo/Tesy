"""No-model freeze and identity checks for the one-arm policy canary."""
from pathlib import Path
import shutil
import tempfile
import unittest

from c2_gate import GateError,strict_json
from c58_resource_canary import REPO,CAP,make,freeze
from host_resource_policy import validate_resource_protocol


class CanaryFreezeTests(unittest.TestCase):
    def test_existing_inventory_freezes_one_cap_and_no_replace(self):
        source=REPO/'results/c55b-resource-policy-20260928T1415Z'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'raw').mkdir()
            for name in ('snapshot.json','resource-policy.json'):
                shutil.copyfile(source/name,root/name)
            freeze(root)
            protocol=strict_json((root/'protocol.json').read_text())
            self.assertEqual(validate_resource_protocol(protocol)['cgroup']['memory_max_bytes'],CAP)
            self.assertNotIn('memory_max_bytes',protocol['limits'])
            self.assertEqual(protocol,make(root)[0])
            with self.assertRaises(FileExistsError):freeze(root)
            (root/'resource-policy.json').write_text('{}')
            with self.assertRaises((GateError,KeyError)):
                make(root)


if __name__=='__main__':unittest.main()
