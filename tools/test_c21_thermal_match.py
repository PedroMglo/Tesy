import unittest

from c17_thermal_recovery import thermal_start_matches


class ThermalStartMatchTest(unittest.TestCase):
    def test_previously_blocked_cool_start_is_admissible_only_in_new_policy(self):
        first = {'cpu_c': 45.75, 'gpu_c': 43, 'nvme_c': 33.85}
        cooler = {'cpu_c': 41.625, 'gpu': {'temperature_c': 39}, 'nvme_c': 32.85}
        self.assertFalse(thermal_start_matches(cooler, first, (2, 3, 3), (55, 55, 55)))
        self.assertTrue(thermal_start_matches(cooler, first, (5, 5, 3), (50, 50, 45)))

    def test_new_policy_still_rejects_hot_or_mismatched_start(self):
        first = {'cpu_c': 42, 'gpu_c': 39, 'nvme_c': 33}
        too_hot = {'cpu_c': 50.1, 'gpu': {'temperature_c': 40}, 'nvme_c': 33}
        too_different = {'cpu_c': 36, 'gpu': {'temperature_c': 39}, 'nvme_c': 33}
        for row in (too_hot, too_different):
            with self.subTest(row=row):
                self.assertFalse(thermal_start_matches(row, first, (5, 5, 3), (50, 50, 45)))
