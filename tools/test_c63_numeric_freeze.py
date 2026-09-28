"""Model-free P14 numeric freeze identity and library drift controls."""
from pathlib import Path
import unittest
from unittest.mock import patch

from c2_gate import GateError
import c63_numeric_run as c63


SOURCE=Path('results/c62-p14-capacity-20260928T1519Z')


class C63NumericFreeze(unittest.TestCase):
    def test_frozen_p14_profile_and_arm_order(self):
        protocol=c63.frozen(SOURCE)
        self.assertEqual(protocol['profile']['ngl'],14)
        self.assertEqual(protocol['profile']['context'],8192)
        self.assertTrue(protocol['profile']['kv_unified'])
        self.assertEqual(protocol['profile']['preload'],'ON')
        self.assertEqual(protocol['resources']['cgroup']['memory_max_bytes'],18*2**30)
        self.assertEqual([x['run_id'] for x in protocol['arms']],
                         ['c63-p14-off01','c63-p14-on01','c63-p14-off02'])
        self.assertEqual(protocol['call_plan']['numeric_states'],250)

    def test_changed_capture_library_rejected_before_model(self):
        original=c63.backend_library_hashes
        def changed(binary,backend):
            value=original(binary,backend)
            if 'boundary_capture' in binary:
                value=dict(value)
                key=next(iter(value));value[key]='0'*64
            return value
        with patch.object(c63,'backend_library_hashes',side_effect=changed):
            with self.assertRaisesRegex(GateError,'library pin'):
                c63.frozen(SOURCE)
