from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import block_causal_gate as gate


class RealBlockWitness(unittest.TestCase):
    source = Path(__file__).resolve().parents[1]/'results/c238-complete-block-causality-20261004/raw/c238-b2.capture'

    def test_actual_raw_optional_biased_stage_and_missing_rows(self):
        actual = gate._index(self.source)
        self.assertFalse(any(row['name']=='ffn_moe_logits_biased' for row in actual))
        result = gate.inspect(self.source, 2)
        self.assertEqual(result['layer_states'], 180)
        self.assertEqual(result['full_logit_rows'], 8)
        for rows in (actual[:-1], actual+actual[:1],
                     [dict(row, state_tokens='0') if i==0 else row for i,row in enumerate(actual)]):
            with patch.object(gate, '_index', return_value=rows), self.assertRaises(ValueError):
                gate.inspect(self.source, 2)

    def test_truncated_witness_is_not_accepted(self):
        actual = self.source/'byte_checks.tsv'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for item in self.source.iterdir():
                if item.name != 'byte_checks.tsv': shutil.copy2(item, root/item.name)
            lines=actual.read_text().splitlines()
            (root/'byte_checks.tsv').write_text('\n'.join(lines[:-1])+'\n')
            with self.assertRaisesRegex(ValueError, 'incomplete/stale'):
                gate.inspect(root, 2)


if __name__=='__main__': unittest.main()
