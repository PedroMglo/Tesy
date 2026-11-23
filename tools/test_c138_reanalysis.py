"""Reanalysis controls: fixed published raw and strict current negative gates."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from c2_gate import GateError
import c135_analyze_slots40_trace as analyze
from c122_trace_validate import validate

class ReanalysisGate(unittest.TestCase):
    def test_real_manifest_and_call_plan(self):
        value=analyze.analyze()
        self.assertEqual(value['trace']['events'],58181)
        self.assertEqual(value['trace']['loads'],2299)

    def test_missing_third_reference(self):
        with patch.object(analyze,'REFERENCE',Path('/tmp/nonexistent-c138-reference')):
            with self.assertRaises((GateError,FileNotFoundError)):analyze.analyze()

    def test_real_trace_mutations(self):
        src=analyze.ROOT_ON/'raw'/f'{analyze.ON}.expert.trace'
        lines=src.read_text().splitlines(); header=lines.index('kind\tseq\tmono_us\tlayer\texpert\tslot\tvictim\tn_tokens\twave\tstate\tlogical_bytes\tcall_id\tgeneration\tcomponent')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'trace'
            for kind in ('UNKNOWN',):
                altered=lines.copy();row=altered[header+1].split('\t');row[0]=kind;altered[header+1]='\t'.join(row)
                path.write_text('\n'.join(altered)+'\n')
                with self.assertRaises(GateError):validate(path)

if __name__=='__main__':unittest.main()
