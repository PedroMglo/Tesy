import copy,unittest
from c2_gate import GateError
from native64_evaluate import evaluate,paired
class UsefulLatencyGate(unittest.TestCase):
    def row(self,profile,t=100):
        return dict(profile=profile,complete=True,natural=True,identity=True,resources=True,deadline=True,samples=True,functional=True,nominal153=True,prefix=True,input_sha256='i',schedule_sha256='s',output='different valid answer',reasoning_tokens=200,**{k:t for k in ('prefill153_s','decode32_s','prefix_prepare_s','T2_first_final_s','SQL_validated_s','cold_prefill_s','cold_first_final_s','T2_completion_s','T3_first_final_s','incremental_prefill_s','decode_seconds_per_reported_output')})
    def test_different_valid_answers_more_reasoning_preserved(self):
        pairs=[(self.row('A32'),self.row('B64',80)) for _ in range(2)]
        pairs[0][1]['output']='another valid SQL';pairs[0][1]['reasoning_tokens']=300
        self.assertEqual(evaluate(pairs,'S')['status'],'GO_S_SCREEN')
    def test_fast_invalid_incomplete_deadline_wrong_profile_and_history(self):
        pairs=[(self.row('A32'),self.row('B64',50)) for _ in range(2)]
        for k,status in [('functional','NO_GO_FUNCTIONAL'),('samples','FAIL_OR_INCOMPLETE_EVIDENCE'),('deadline','FAIL_OR_INCOMPLETE_EVIDENCE'),('nominal153','INCONCLUSIVE_NOMINAL153'),('prefix','INCONCLUSIVE_NOMINAL153')]:
            bad=copy.deepcopy(pairs);bad[0][1][k]=False;self.assertEqual(evaluate(bad,'S')['status'],status)
        bad=copy.deepcopy(pairs);bad[0][1]['profile']='A32'
        with self.assertRaises(GateError):evaluate(bad,'S')
    def test_fixed_work_and_percentages_per_pair(self):
        pairs=[(self.row('A32',100),self.row('B64',80)),(self.row('A32',10),self.row('B64',9))]
        result=evaluate(pairs,'W');self.assertEqual(result['medians']['prefill153_s'],15)
        pairs[1][1]['input_sha256']='wrong'
        with self.assertRaises(GateError):evaluate(pairs,'W')
        for a,b in [(0,1),(1,float('nan'))]:
            with self.assertRaises(GateError):paired(a,b)
