import tempfile
from pathlib import Path
import struct
import unittest
from c152_snapshot_read import snapshot,routes

ROOT=Path(__file__).resolve().parents[1]/'results/c152-slots44-snapshot-model-free-20260930T0215Z'

class NativeSnapshot(unittest.TestCase):
    def test_native_golden_remap_decay_and_multiplicity(self):
        a=snapshot(ROOT/'golden-v3-remap/before.snap',physical=False)
        b=snapshot(ROOT/'golden-v3-remap/after.snap',physical=False)
        r=routes(ROOT/'golden-v3-remap/routes.bin')
        self.assertEqual((a['n_calls'],b['n_calls']),(63,64))
        self.assertEqual(b['layers'][0]['slot_expert'],[0,1,4,5])
        self.assertEqual(b['layers'][0]['route_hotness'][0],(2**32-1)//2)
        self.assertEqual(r[0]['ids'],[0,1,4,5,0,1,4,5])
        self.assertGreaterEqual(r[0]['transition_seq'],0)

    def test_native_loading_pending_commit_and_duplicate_queue(self):
        s=snapshot(ROOT/'golden-v3-loading/after.snap',physical=False)
        self.assertEqual(s['owned'][0]['phase'],2)
        self.assertEqual(s['layers'][0]['slot_claimed'][1],1)
        self.assertEqual(s['queue'][0]['generation'],s['queue'][1]['generation'])
        self.assertNotEqual(s['queue'][0]['work_id'],s['queue'][1]['work_id'])

    def test_native_wave_does_not_update_remap_hotness(self):
        s=snapshot(ROOT/'golden-v3-wave/after.snap',physical=False)
        self.assertEqual(s['layers'][0]['n_waves'],2)
        self.assertEqual(s['layers'][0]['route_hotness'][0],1)
        self.assertEqual(routes(ROOT/'golden-v3-wave/routes.bin')[0]['mode'],1)

    def test_snapshot_endian_truncation_overflow_unknown_version(self):
        original=(ROOT/'golden-v3-remap/after.snap').read_bytes()
        cases=[original[:-1],original+b'x',b'WRONGMAG'+original[8:]]
        for offset,value in ((8,0),(12,2),(276+14*8,1)):
            b=bytearray(original);struct.pack_into('<I' if offset==8 else '<q',b,offset,value);cases.append(bytes(b))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'mutant.snap'
            for b in cases:
                p.write_bytes(b)
                with self.assertRaises(ValueError):snapshot(p,physical=False)

    def test_route_bad_id_truncation_and_duplicate_topk(self):
        original=(ROOT/'golden-v3-remap/routes.bin').read_bytes()
        cases=[original[:-1]]
        for offset,value in ((64,128),(64+8,0),(24,7)):
            b=bytearray(original);struct.pack_into('<q',b,offset,value);cases.append(bytes(b))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'mutant.routes'
            for b in cases:
                p.write_bytes(b)
                with self.assertRaises(ValueError):routes(p)


class SnapshotIdentityAndBounds(unittest.TestCase):
    def test_hash_expectation_and_partial(self):
        import tempfile
        p=ROOT/'golden-v3-loading/after.snap';hashes=['0'*64]*4
        snapshot(p,physical=False,expected_hashes=hashes)
        with self.assertRaisesRegex(ValueError,'identity hashes'):snapshot(p,physical=False,expected_hashes=['f'*64]*4)
        with tempfile.TemporaryDirectory() as d:
            q=Path(d)/'failed.partial';q.write_bytes(p.read_bytes())
            with self.assertRaises(ValueError):snapshot(q,physical=False)
    def test_snapshot_and_route_capacity_bound(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'too-large.snap';p.write_bytes(b'x'*(1024*1024+1))
            with self.assertRaises(ValueError):snapshot(p,physical=False)
            p=Path(d)/'too-large.routes';p.write_bytes(b'x'*(8*1024*1024+8))
            with self.assertRaises(ValueError):routes(p)
    def test_native_v4_journal(self):
        from c152_journal_validate import validate
        root=ROOT.parent/'c156-snapshot-gates-20260930T1000Z'
        for mode in ('remap','loading','wave'):
            with self.subTest(mode=mode):validate(root/('native-v4-'+mode)/'journal.trace',physical=False)

if __name__=='__main__':unittest.main()
