import unittest
from block_verifier_contract import verify,budgets,paired_gain


class GreedyBlock(unittest.TestCase):
    def test_complete_acceptance_includes_bonus_not_anchor(self):
        a=verify([21,22,23,24],[21,22,23])
        self.assertEqual(a.tokens,(21,22,23,24))
        self.assertEqual(a.consumed_inputs,4)
        self.assertEqual(a.next_pending_anchor,24)

    def test_each_rejection_and_rollback_position(self):
        for j in range(3):
            proposal=[21,22,23];proposal[j]=99
            a=verify([21,22,23,24],proposal)
            self.assertEqual(a.tokens,tuple([21,22,23,24][:j+1]))
            self.assertEqual(a.rejected_at,j)
            self.assertEqual(a.consumed_inputs,j+1)
            self.assertEqual(a.next_pending_anchor,21+j)

    def test_eos_and_cap_do_not_publish_future_suffix(self):
        for a in (verify([21,22,23,24],[21,22,23],eos=[22]),
                  verify([21,22,23,24],[21,22,23],remaining=2)):
            self.assertEqual(a.tokens,(21,22))
            self.assertIsNone(a.next_pending_anchor)

    def test_complete_row_and_output_reserve_required(self):
        for rows,proposal in [([],[]),([1],[2]),([1,2],[]),([-1,2],[1])]:
            with self.assertRaises(ValueError):verify(rows,proposal)
        with self.assertRaises(ValueError):verify([1,2],[1],remaining=0)

    def test_real_break_even_and_draft_budget(self):
        out=budgets(4,4,2,accepted=4,gain=.15)
        self.assertEqual(out['T_AR_s'],1)
        self.assertEqual(out['L_break_even'],2)
        self.assertAlmostEqual(out['D_budget_s'],1.4)
        self.assertLess(budgets(4,4,2,accepted=1)['D_budget_s'],0)
        self.assertEqual(paired_gain(4,2),50)
        for bad in (0,float('nan'),float('inf'),None):
            with self.assertRaises(ValueError):paired_gain(4,bad)


if __name__=='__main__':unittest.main()
