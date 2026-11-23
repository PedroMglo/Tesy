"""P14 capacity freeze checks with an already validated host snapshot, no model run."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from c2_gate import GateError
from c62_placement_admission import make


SOURCE=Path('results/c61-wave-boundary-20260928T1509Z')


class C62PlacementFreeze(unittest.TestCase):
    def test_one_variable_and_two_gated_modes(self):
        init,init_config,init_tasks=make(SOURCE,'init')
        forward,forward_config,forward_tasks=make(SOURCE,'forward')
        for protocol,config in ((init,init_config),(forward,forward_config)):
            command=config['server_command']
            self.assertEqual(command[command.index('-ngl')+1],'14')
            self.assertEqual(command[command.index('-c')+1],'8192')
            self.assertEqual(command[command.index('-ub')+1],'32')
            self.assertEqual(protocol['resources']['cgroup']['memory_max_bytes'],18*2**30)
        self.assertEqual(init_tasks,[])
        self.assertEqual(len(forward_tasks),1)
        self.assertEqual(forward['c62']['prompt_tokens_admission_band'],[480,540])

    def test_changed_inventory_model_identity_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for name in ('snapshot.json','resource-policy.json'):
                shutil.copyfile(SOURCE/name,root/name)
            snapshot=json.loads((root/'snapshot.json').read_text())
            snapshot['model_stat']['inode']+=1
            (root/'snapshot.json').write_text(json.dumps(snapshot))
            with self.assertRaisesRegex(GateError,'inventory'):
                make(root,'init')
