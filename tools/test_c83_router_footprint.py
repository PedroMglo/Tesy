"""Discriminants for the captured router footprint input contract."""

import copy
import csv
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

from c2_gate import GateError
from c83_router_footprint import ROOT, checked_rows, sha


class RouterFootprintInputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.capture = self.root / 'raw/capture'
        self.capture.mkdir(parents=True)
        source = ROOT / 'raw/c76b-p12-session-wave-on01.capture'
        with (source / 'index.tsv').open(newline='') as stream:
            reader = csv.DictReader(stream, delimiter='\t')
            self.header = reader.fieldnames
            self.rows = [row for row in reader if row['name'] == 'ffn_moe_topk']
        self.manifest = {'raw_sha256': {}}
        for row in self.rows:
            path = self.capture / row['file']
            shutil.copyfile(source / row['file'], path)
            self._rehash(row['file'])

    def _rehash(self, file):
        path = self.capture / file
        self.manifest['raw_sha256'][str(path.relative_to(self.root))] = {
            'bytes': path.stat().st_size, 'sha256': sha(path)}

    def _check(self):
        index = self.capture / 'index.tsv'
        with index.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=self.header, delimiter='\t')
            writer.writeheader()
            writer.writerows(self.rows)
        return checked_rows(index, self.capture, self.manifest)

    def test_valid_control(self):
        self.assertEqual(250, len(self._check()))

    def test_empty_payload(self):
        file = self.rows[0]['file']
        (self.capture / file).write_bytes(b'')
        self._rehash(file)
        with self.assertRaises(GateError):
            self._check()

    def test_declared_stride(self):
        self.rows[0]['nb'] = '4,4,128,128'
        with self.assertRaises(GateError):
            self._check()

    def test_duplicate_and_missing_state(self):
        saved = self.rows.pop()
        with self.assertRaises(GateError):
            self._check()
        self.rows.append(saved)
        self.rows.append(copy.copy(saved))
        with self.assertRaises(GateError):
            self._check()

    def test_invalid_router_id_with_valid_hash(self):
        row = next(row for row in self.rows if row['phase'] == 'decode0')
        path = self.capture / row['file']
        payload = bytearray(path.read_bytes())
        struct.pack_into('<i', payload, 0, 128)
        path.write_bytes(payload)
        self._rehash(row['file'])
        with self.assertRaises(GateError):
            self._check()


if __name__ == '__main__':
    unittest.main()
