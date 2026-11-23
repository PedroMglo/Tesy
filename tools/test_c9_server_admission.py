"""Small fault set for the new server admission receipt."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from c2_gate import GateError
from c9_server_admission import RUN_ID, validate_receipt
from run_bounded import sha256


class AdmissionReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'raw').mkdir()
        (self.root / 'protocol.json').write_text('{}\n')
        self.config = {'mode': 'synthetic', 'explicit_env': {}}
        self.identity = {'pid': 123, 'start_ticks': 456,
                         'cgroup_path': '/test.scope', 'cgroup_inode': 789}
        self.cg = {'memory_max': 18*2**30, 'swap_max': 0, 'swap_current': 0,
                   'memory_peak': 100, 'events': {'max': 0, 'oom': 0, 'oom_kill': 0},
                   'events_local': {'max': 0, 'oom': 0, 'oom_kill': 0}}
        self.protocol = {'identity': {'library_sha256': {'libtest.so': '0'*64}},
                         'limits': {'rss_max_bytes': 16*2**30,
                                    'memory_max_bytes': int(16.5*2**30),
                                    'gpu_max_mib': 6500,
                                    'min_mem_available_bytes': 6*2**30}}
        pre = {'protocol_sha256': sha256(self.root / 'protocol.json'),
               'config': dict(self.config, run_id=RUN_ID),
               'relevant_environment': {},
               'actually_loaded_backend_libraries_sha256': {'libtest.so': '0'*64},
               'ready_elapsed_s': 1.0, 'cgroup_start': copy.deepcopy(self.cg)}
        self.raw = {'stop_reasons': [], 'returncode': 0, 'results': [],
                    'preflight': pre, 'launch_identity': self.identity,
                    'cgroup_end': copy.deepcopy(self.cg), 'elapsed_s': 1.3,
                    'sample_count': 2, 'source_sha256': {}}
        launch = {'preflight_sha256': None, 'process_identity': self.identity}
        prefile = self.root / 'raw' / f'{RUN_ID}.preflight.json'
        prefile.write_text('{}\n')
        launch['preflight_sha256'] = sha256(prefile)
        (self.root / 'raw' / f'{RUN_ID}.launch.json').write_text(json.dumps(launch))
        self.samples = []
        for t in (.1, 1.0):
            self.samples.append({'elapsed_s': t, 'pid': 123,
                                 'process_identity': copy.deepcopy(self.identity),
                                 'proc': {'VmRSS': 100, 'VmSwap': 0, 'VmHWM': 100},
                                 'cgroup': copy.deepcopy(self.cg),
                                 'gpu': {'used_mib': 10, 'temperature_c': 45},
                                 'thermal': {'cpu_tctl_c': 50, 'nvme_composite_c': 40},
                                 'mem_available_bytes': 7*2**30})
        for suffix in ('.preflight.json', '.launch.json', '.stdout', '.stderr', '.samples.jsonl'):
            path = self.root / 'raw' / f'{RUN_ID}{suffix}'
            if not path.exists(): path.write_text('')
            self.raw['source_sha256'][suffix] = sha256(path)

    def validate(self):
        return validate_receipt(self.protocol, self.config, self.raw, self.samples, self.root)

    def test_valid_admission(self):
        self.assertEqual(self.validate()['rss_bytes'], 100)

    def test_unexpected_library(self):
        self.raw['preflight']['actually_loaded_backend_libraries_sha256']['extra.so'] = '1'*64
        with self.assertRaisesRegex(GateError, 'mapped backend library'):
            self.validate()

    def test_missing_launch_receipt(self):
        (self.root / 'raw' / f'{RUN_ID}.launch.json').unlink()
        with self.assertRaises(FileNotFoundError):
            self.validate()

    def test_missing_rss_and_oom(self):
        del self.samples[0]['proc']['VmRSS']
        with self.assertRaisesRegex(GateError, 'process memory'):
            self.validate()
        self.samples[0]['proc']['VmRSS'] = 100
        self.samples[1]['cgroup']['events']['oom'] = 1
        with self.assertRaisesRegex(GateError, 'cgroup identity'):
            self.validate()

    def test_timestamp_after_end(self):
        self.samples[-1]['elapsed_s'] = 2.0
        with self.assertRaisesRegex(GateError, 'timestamp'):
            self.validate()


if __name__ == '__main__':
    unittest.main()
