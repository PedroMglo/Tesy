"""Directed C99 causal-start negative and boundary cases."""

import math
import unittest

from c2_gate import GateError
from c99_server_wave_screen import thermal_match


def obs(cpu, gpu, nvme):
    return {'thermal':{'cpu_tctl_c':cpu,
                       'nvme_composite_by_sensor':{'nvme-pci-c100':nvme}},
            'gpu':{'temperature_c':gpu}}


class MatchedStart(unittest.TestCase):
    def test_exact_boundaries_and_outside(self):
        anchor=obs(50,45,35)
        self.assertTrue(thermal_match(anchor,obs(53,48,37),'nvme-pci-c100'))
        self.assertTrue(thermal_match(anchor,obs(47,42,33),'nvme-pci-c100'))
        self.assertFalse(thermal_match(anchor,obs(53.01,45,35),'nvme-pci-c100'))
        self.assertFalse(thermal_match(anchor,obs(50,48.01,35),'nvme-pci-c100'))
        self.assertFalse(thermal_match(anchor,obs(50,45,37.01),'nvme-pci-c100'))

    def test_missing_and_nonfinite_do_not_match(self):
        anchor=obs(50,45,35)
        for changed in (obs(math.nan,45,35),obs(50,math.inf,35),obs(50,45,-math.inf)):
            with self.assertRaises(GateError):
                thermal_match(anchor,changed,'nvme-pci-c100')
        with self.assertRaises(GateError):
            thermal_match(anchor,obs(50,45,35),'wrong-sensor')


if __name__=='__main__':
    unittest.main()
