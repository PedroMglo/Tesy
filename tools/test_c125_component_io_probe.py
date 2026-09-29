"""Focused model-free offset and direct-read boundary controls for C125."""

import os
import tempfile
import unittest

from c2_gate import GateError
from c125_component_io_probe import groups, inventory_offsets, read_component, serial_expert


class C125ProbeTest(unittest.TestCase):
    def test_exact_frozen_workload(self):
        offsets=inventory_offsets()
        self.assertEqual(len(offsets),108)
        self.assertEqual(offsets[(0,'ffn_down_exps')][1],4406400)
        workload,total=groups()
        self.assertEqual(len(workload),1012)
        self.assertEqual(sum(len(group) for group in workload),1509)
        self.assertEqual(total,19947772800)
        self.assertLessEqual(max(len(group) for group in workload),4)

    def test_unaligned_expert_offset_and_short_read(self):
        with tempfile.TemporaryFile() as f:
            f.write(b'a'*8192)
            f.flush()
            self.assertEqual(read_component(f.fileno(),(37,1000)),1000)
            self.assertEqual(serial_expert(f.fileno(),[(37,1000)]*3),3000)
            with self.assertRaisesRegex(GateError,'short direct read'):
                read_component(f.fileno(),(9000,1000))


if __name__=='__main__':unittest.main()
