import unittest
from expert_score_corpus_family_gate import eligibility

class Population(unittest.TestCase):
    def test_frozen_minimum(self):
        self.assertTrue(eligibility([64]*8)['admitted'])
        self.assertFalse(eligibility([63]*8)['admitted'])
        self.assertFalse(eligibility([0]+[128]*7)['admitted'])
        self.assertFalse(eligibility([15]+[128]*7)['admitted'])
    def test_no_missing_fake_or_unbounded_rows(self):
        for x in ([128]*7,[128]*9,[float('nan')]+[128]*7,[None]+[128]*7,[True]+[128]*7,[129]+[128]*7):
            with self.assertRaises(ValueError):eligibility(x)
if __name__=='__main__':unittest.main()
