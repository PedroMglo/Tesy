"""Discriminating C61 schema and historical failure fixture, no model."""
import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from c2_gate import GateError
from c61_boundary_gate import compare, validate, CORE


SRC = Path('results/c48-skip-boundary-20260928T0954Z/raw')


def fixture(source, target):
    target.mkdir()
    with (source/'index.tsv').open() as f:
        rows = [r for r in csv.DictReader(f, delimiter='\t')
                if r['phase'] == 'prefill0' and r['layer'] == '0']
    with (target/'index.tsv').open('x', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter='\t')
        writer.writeheader(); writer.writerows(rows)
    for row in rows:
        shutil.copyfile(source/row['file'], target/row['file'])
    for name in ('masked.tsv','phases.txt','stages.txt'):
        shutil.copyfile(source/name,target/name)
    for name in ('byte_checks.tsv','route_prestate.tsv'):
        with (source/name).open() as f:
            values=list(csv.DictReader(f,delimiter='\t'))
        with (target/name).open('x',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(values[0]),delimiter='\t')
            writer.writeheader()
            writer.writerows(r for r in values if r['phase']=='prefill0' and r['layer']=='0')
    for phase in ('prefill_final','decode0','decode1','decode7','decode31'):
        name=phase+'.logits.f32'
        shutil.copyfile(source/name,target/name)


class C61BoundaryGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.root=Path(cls.temp.name)
        cls.off=cls.root/'off';cls.on=cls.root/'on'
        fixture(SRC/'c48-g2-off01.capture',cls.off)
        fixture(SRC/'c48-g2-on01.capture',cls.on)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_historical_same_profile_fail_is_seen(self):
        result=compare(self.off,self.on)
        self.assertEqual(result['status'],'FAIL_SAME_PROFILE_FIDELITY')
        self.assertTrue(any(x.get('stage')=='ffn_moe_out' for x in result['mismatch']))

    def test_valid_same_profile_control(self):
        # Keep ON parked-wave IDs; replace only observed active states/logits.
        with tempfile.TemporaryDirectory() as temp:
            candidate=Path(temp)/'on'
            shutil.copytree(self.on,candidate)
            with (self.off/'index.tsv').open() as f:
                for row in csv.DictReader(f,delimiter='\t'):
                    if row['name'] in CORE:
                        shutil.copyfile(self.off/row['file'],candidate/row['file'])
            for phase in ('prefill_final','decode0','decode1','decode7','decode31'):
                name=phase+'.logits.f32'
                shutil.copyfile(self.off/name,candidate/name)
            self.assertEqual(compare(self.off,candidate)['status'],'SAME_PROFILE_BITWISE_PASS')
            victim=candidate/'prefill0_0_ffn_moe_out_25.bin'
            victim.write_bytes(victim.read_bytes()[:-4])
            with self.assertRaisesRegex(GateError,'payload byte count'):
                validate(candidate,True)

    def test_zero_payload_and_wrong_width_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            bad=Path(temp)/'off';shutil.copytree(self.off,bad)
            (bad/'prefill0_0_ffn_moe_out_25.bin').write_bytes(b'')
            with self.assertRaisesRegex(GateError,'payload byte count'):
                validate(bad,False)
            shutil.copyfile(self.off/'prefill0_0_ffn_moe_out_25.bin',
                            bad/'prefill0_0_ffn_moe_out_25.bin')
            index=bad/'index.tsv'
            index.write_text(index.read_text().replace('2880,32,1,1','1,32,1,1',1))
            with self.assertRaisesRegex(GateError,'shape'):
                validate(bad,False)
