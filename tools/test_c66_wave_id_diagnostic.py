"""The C66 receipt must distinguish a routed-ID abort from unrelated failures."""
import unittest
from c66_wave_id_diagnostic import diagnostic

class InvalidIdReceiptTest(unittest.TestCase):
    def test_exact_location_and_value(self):
        log='MoE wave routed-ID diagnostic: layer=1 wave=0 index=17 id=-1 n_expert=128 n=128 ne0=4 ne1=32'
        self.assertEqual(diagnostic(log),{'layer':1,'wave':0,'index':17,'id':-1,
            'n_expert':128,'n':128,'ne0':4,'ne1':32})

    def test_other_abort_has_no_routed_id_attribution(self):
        self.assertIsNone(diagnostic('GGML_ASSERT(e >= 0 && e < n_expert)'))
        self.assertIsNone(diagnostic('MoE wave routed-ID diagnostic: layer=1 id=129'))

if __name__=='__main__':unittest.main()
