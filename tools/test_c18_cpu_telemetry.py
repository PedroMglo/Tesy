"""Mutants distinguishing warning, physical stop and incomplete diagnostics."""

import copy
import unittest
from pathlib import Path

from c2_gate import GateError
from c18_cpu_telemetry import (summarize_samples, thermal_stop_reason,
                               clock_collapse, read_effective_clock)
from c9_server_admission import cpu_guard_violation


class Cpu100PolicyTests(unittest.TestCase):
    def test_effective_clock_one_zero_is_recorded_and_repeated_invalid_fails(self):
        policy=Path('policy7')
        readings=iter((0,3300000))
        value, diagnostic=read_effective_clock(policy, lambda: next(readings))
        self.assertEqual(value,3300000)
        self.assertEqual(diagnostic,{'policy':'policy7','first_khz':0,
                                      'second_khz':3300000})
        readings=iter((21786195,3300000))
        value, diagnostic=read_effective_clock(policy, lambda: next(readings))
        self.assertEqual(value,3300000)
        self.assertEqual(diagnostic,{'policy':'policy7','first_khz':21786195,
                                      'second_khz':3300000})
        for values in ((0,0),(0,10000000),(-1,), (10000000,10000000),
                       (21786195,0),(21786195,-1)):
            with self.subTest(values=values), self.assertRaisesRegex(GateError,'policy7'):
                readings=iter(values)
                read_effective_clock(policy,lambda: next(readings))

    def test_warning_is_not_stop_and_tjmax_is(self):
        diagnostics = {'processor_cooling_max_state': 0}
        self.assertIsNone(thermal_stop_reason(95.125, diagnostics, [3000] * 12, [2900] * 5))
        self.assertEqual(thermal_stop_reason(100, diagnostics, [3000] * 12, [2900] * 5),
                         'CPU_TJMAX_100')
        new_protocol = {'c18': {}, 'limits': {'cpu_max_c': 100}}
        self.assertFalse(cpu_guard_violation(95.125, new_protocol))
        self.assertTrue(cpu_guard_violation(100, new_protocol))
        self.assertTrue(cpu_guard_violation(95.125, {'limits': {'cpu_max_c': 95}}))

    def test_explicit_cooling_and_sustained_clock_drop_stop(self):
        diagnostics = {'processor_cooling_max_state': 1}
        self.assertEqual(thermal_stop_reason(94, diagnostics, [3000] * 12, []),
                         'CPU_PROCESSOR_COOLING_ACTIVE')
        diagnostics['processor_cooling_max_state'] = 0
        self.assertFalse(clock_collapse([3000] * 12, [1400] * 4, 5))
        self.assertEqual(thermal_stop_reason(96, diagnostics, [3000] * 12, [1400] * 5),
                         'CPU_CLOCK_COLLAPSE_WITH_THERMAL_WARNING')

    def test_complete_samples_pass_and_missing_mutant_fails(self):
        def sample(t, cpu, power):
            return {'elapsed_s': t, 'thermal': {'cpu_tctl_c': cpu},
                    'cpu_diagnostics': {
                        'effective_clock_mhz_by_policy': {f'policy{i}': 3000 for i in range(12)},
                        'effective_clock_median_mhz': 3000,
                        'package_power_w': power, 'package_energy_uj': 1000000 + t * 30000000,
                        'thermal_warning': cpu >= 95, 'processor_cooling_max_state': 0,
                        'processor_cooling_states': {'cooling_device8': 0}}}
        good = [sample(0, 94, None), sample(1, 95.125, 30)]
        self.assertEqual(summarize_samples(good, require_safe=True)['cpu_warning_sample_count'], 1)
        retried=copy.deepcopy(good)
        retried[1]['cpu_diagnostics']['effective_clock_transient_zero_reads']=[
            {'policy':'policy1','first_khz':0,'second_khz':3000000}]
        self.assertEqual(summarize_samples(retried,require_safe=True)[
            'cpu_effective_clock_transient_zero_read_count'],1)
        retried[1]['cpu_diagnostics']['effective_clock_transient_zero_reads'][0]['second_khz']=0
        with self.assertRaises(GateError):
            summarize_samples(retried,require_safe=True)
        high=copy.deepcopy(good)
        high[1]['cpu_diagnostics']['effective_clock_transient_high_reads']=[
            {'policy':'policy1','first_khz':21786195,'second_khz':3000000}]
        self.assertEqual(summarize_samples(high,require_safe=True)[
            'cpu_effective_clock_transient_high_read_count'],1)
        high[1]['cpu_diagnostics']['effective_clock_transient_high_reads'][0]['second_khz']=21786195
        with self.assertRaises(GateError):
            summarize_samples(high,require_safe=True)
        for mutant in ('missing', 'cooling', 'hundred'):
            bad = copy.deepcopy(good)
            if mutant == 'missing':
                del bad[1]['cpu_diagnostics']
            elif mutant == 'cooling':
                bad[1]['cpu_diagnostics']['processor_cooling_states']['cooling_device8'] = 1
                bad[1]['cpu_diagnostics']['processor_cooling_max_state'] = 1
            else:
                bad[1]['thermal']['cpu_tctl_c'] = 100
                bad[1]['cpu_diagnostics']['thermal_warning'] = True
            with self.subTest(mutant=mutant), self.assertRaises(GateError):
                summarize_samples(bad, require_safe=True)


if __name__ == '__main__':
    unittest.main()
