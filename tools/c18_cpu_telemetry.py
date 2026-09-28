"""Read-only CPU clock, package energy and ACPI thermal mitigation telemetry."""

from pathlib import Path
from statistics import median
import math

from c2_gate import GateError


POLICIES = Path('/sys/devices/system/cpu/cpufreq')
RAPL = Path('/sys/class/powercap/intel-rapl:0')
COOLING = Path('/sys/class/thermal')


def read_effective_clock(policy, read_khz=None):
    """Record and reread a single zero; keep persistent/other invalid reads fatal."""
    reader = read_khz or (lambda: int((policy / 'cpuinfo_avg_freq').read_text()))
    first = reader()
    if type(first) is not int:
        raise GateError(f'CPU effective frequency invalid {policy.name}: {first!r}')
    if first == 0:
        second = reader()
        if type(second) is int and 0 < second < 10_000_000:
            return second, {'policy': policy.name, 'first_khz': first,
                            'second_khz': second}
        raise GateError(f'CPU effective frequency out of range {policy.name}: '
                        f'first={first!r}, reread={second!r}')
    if not 0 < first < 10_000_000:
        raise GateError(f'CPU effective frequency out of range {policy.name}: '
                        f'first={first!r}')
    return first, None


def capture():
    clocks = {}
    transient_zero_reads = []
    for policy in sorted(POLICIES.glob('policy[0-9]*'), key=lambda p: int(p.name[6:])):
        value, transient = read_effective_clock(policy)
        clocks[policy.name] = value / 1000
        if transient is not None:
            transient_zero_reads.append(transient)
    if len(clocks) < 12:
        raise GateError('CPU effective clock coverage incomplete')
    if (RAPL / 'name').read_text().strip() != 'package-0':
        raise GateError('CPU package energy identity changed')
    energy = int((RAPL / 'energy_uj').read_text())
    energy_range = int((RAPL / 'max_energy_range_uj').read_text())
    if not 0 <= energy < energy_range:
        raise GateError('CPU package energy out of range')
    states = {}
    for item in COOLING.glob('cooling_device[0-9]*'):
        if (item / 'type').read_text().strip() == 'Processor':
            state = int((item / 'cur_state').read_text())
            maximum = int((item / 'max_state').read_text())
            if not 0 <= state <= maximum:
                raise GateError('processor cooling state out of range')
            states[item.name] = state
    if not states:
        raise GateError('processor cooling state unavailable')
    return {'effective_clock_mhz_by_policy': clocks,
            'effective_clock_median_mhz': median(clocks.values()),
            'effective_clock_transient_zero_reads': transient_zero_reads,
            'package_energy_uj': energy,
            'package_energy_range_uj': energy_range,
            'processor_cooling_states': states,
            'processor_cooling_max_state': max(states.values())}


def package_power_w(previous, current, seconds):
    if previous is None:
        return None
    if seconds <= 0 or current['package_energy_range_uj'] != previous['package_energy_range_uj']:
        raise GateError('CPU package power interval invalid')
    delta = (current['package_energy_uj'] - previous['package_energy_uj']) % current['package_energy_range_uj']
    watts = delta / 1_000_000 / seconds
    if not 0 <= watts < 1000:
        raise GateError('CPU package power out of range')
    return watts


def clock_collapse(prewarning_mhz, warning_mhz, consecutive):
    """Conservative stop proxy; temporal association is not a causal proof."""
    if len(prewarning_mhz) < 10 or len(warning_mhz) < consecutive:
        return False
    baseline = median(prewarning_mhz[-30:])
    return all(value < baseline * 0.5 for value in warning_mhz[-consecutive:])


def thermal_stop_reason(cpu_c, diagnostics, prewarning_mhz, warning_mhz):
    if cpu_c >= 100:
        return 'CPU_TJMAX_100'
    if diagnostics['processor_cooling_max_state'] > 0:
        return 'CPU_PROCESSOR_COOLING_ACTIVE'
    if cpu_c >= 95 and clock_collapse(prewarning_mhz, warning_mhz, 5):
        return 'CPU_CLOCK_COLLAPSE_WITH_THERMAL_WARNING'
    return None


def summarize_samples(samples, *, require_safe):
    """Check C18 telemetry coverage and return physical diagnostics."""
    if len(samples) < 2:
        raise GateError('C18 telemetry samples absent')
    clocks, powers, temperatures, gpu_powers = [], [], [], []
    warnings = 0
    max_cooling = 0
    energy = []
    policy_set = None
    transient_zero_count = 0
    for i, sample in enumerate(samples):
        diag = sample.get('cpu_diagnostics')
        if type(diag) is not dict:
            raise GateError(f'C18 CPU diagnostics absent at sample {i}')
        keys = set(diag['effective_clock_mhz_by_policy'])
        if policy_set is None:
            policy_set = keys
        if keys != policy_set or len(keys) < 12:
            raise GateError('CPU frequency policy coverage changed')
        retries = diag.get('effective_clock_transient_zero_reads', [])
        if type(retries) is not list:
            raise GateError('CPU transient zero diagnostic malformed')
        for retry in retries:
            if type(retry) is not dict or set(retry) != {'policy','first_khz','second_khz'} or \
               retry['policy'] not in keys or retry['first_khz'] != 0 or \
               type(retry['second_khz']) is not int or not 0 < retry['second_khz'] < 10_000_000 or \
               diag['effective_clock_mhz_by_policy'][retry['policy']] != retry['second_khz']/1000:
                raise GateError('CPU transient zero diagnostic inconsistent')
        transient_zero_count += len(retries)
        clock = diag['effective_clock_median_mhz']
        if type(clock) not in (float, int) or not math.isfinite(clock) or clock <= 0:
            raise GateError('CPU effective clock invalid')
        power = diag['package_power_w']
        if i and (type(power) not in (float, int) or not math.isfinite(power) or
                  not 0 <= power < 1000):
            raise GateError('CPU package power missing/invalid')
        cpu = sample['thermal']['cpu_tctl_c']
        if diag['thermal_warning'] != (cpu >= 95):
            raise GateError('CPU warning marker inconsistent')
        if diag['processor_cooling_max_state'] != max(diag['processor_cooling_states'].values()):
            raise GateError('processor cooling marker inconsistent')
        clocks.append(clock)
        if power is not None:
            powers.append(power)
        temperatures.append(cpu)
        gpu_power = sample.get('gpu', {}).get('power_w')
        if type(gpu_power) in (int, float) and math.isfinite(gpu_power) and gpu_power >= 0:
            gpu_powers.append(gpu_power)
        warnings += int(diag['thermal_warning'])
        max_cooling = max(max_cooling, diag['processor_cooling_max_state'])
        energy.append(diag['package_energy_uj'])
    if require_safe and (max(temperatures) >= 100 or max_cooling):
        raise GateError('CPU thermal stop condition observed in completed run')
    return {'sample_count': len(samples), 'cpu_max_c': max(temperatures),
            'cpu_warning_sample_count': warnings, 'cpu_warning_observed': bool(warnings),
            'cpu_effective_clock_min_mhz': min(clocks),
            'cpu_effective_clock_median_mhz': median(clocks),
            'cpu_effective_clock_max_mhz': max(clocks),
            'cpu_package_power_max_w': max(powers) if powers else None,
            'cpu_package_power_median_w': median(powers) if powers else None,
            'gpu_power_max_w': max(gpu_powers) if gpu_powers else None,
            'processor_cooling_max_state': max_cooling,
            'cpu_policy_count': len(policy_set),
            'cpu_effective_clock_transient_zero_read_count': transient_zero_count,
            'power_source': 'package-0 RAPL energy counter; interval power estimate',
            'clock_source': 'cpuinfo_avg_freq per cpufreq policy',
            'explicit_thermal_flag_source': 'ACPI Processor cooling cur_state; AMD hardware flag unavailable'}
