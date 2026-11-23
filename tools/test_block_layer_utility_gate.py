import copy
import unittest
from block_layer_utility_gate import validate, classify, paired, METRICS


def sample(profile='A'):
    state = dict(pending_queue=0,n_calls=9,layers=[dict(layer=i,slot_expert=list(range(40)),slot_state=[2]*40,slot_generation=[1]*40,slot_claimed=[False]*40) for i in range(36)])
    task = dict(messages=[dict(role='user',content='fixture')])
    v = dict(status='COMPLETE_FREE_NATIVE_UTILITY_OBSERVATION',profile=profile,case='code',official_input_ids=[1]*2100,provided_messages=task['messages'],cache_prefix_n=1947,evaluated_n=153,cap=768,deadline_s=360,
             native_output_ids=[3,200002],events=[dict(native_id=3,terminal_eog=False,observed_s=11),dict(native_id=200002,terminal_eog=True,observed_s=12)],output_count_including_eog=2,decode_forward_calls=1,finish_reason='stop',
             prefix_preparation_s=60,incremental_prefill_s=10,cold_prefill_s=70,cold_first_final_s=71,completion_s=12,decode_s=2,decode_seconds_per_native_output=1,request_start_monotonic_s=100,completion_monotonic_s=112,
             first_reasoning_s=None,first_final_s=11,raw_generated_text='done',reasoning='',final='done',native_parser_error='',initial=state,final_state=copy.deepcopy(state))
    return v,dict(ids=v['official_input_ids'],task=task)


def row(i,profile,scale=1,good=True):
    v,_=sample(profile);a=classify(v,dict(status='PASS' if good else 'FAIL'),113,114)
    a['metrics']={k:scale*10 if k!='validated_s' or good else None for k in METRICS}
    return dict(id=str(i),profile=profile,observation=v,assessment=a)


class Gates(unittest.TestCase):
    def test_real_receipt_contract_counterproofs(self):
        v,s=sample();validate(v,s,'A','code')
        for k,bad in [('official_input_ids',[]),('events',[]),('native_output_ids',[]),('profile','B'),('cache_prefix_n',2044),('completion_s',float('nan')),('incremental_prefill_s',0),('provided_messages',[]),('finish_reason','error'),('first_final_s',99)]:
            x=copy.deepcopy(v);x[k]=bad
            with self.assertRaises(ValueError,msg=k):validate(x,s,'A','code')
        x=copy.deepcopy(v);x['initial']['layers']=[]
        with self.assertRaises(ValueError):validate(x,s,'A','code')

    def test_actual_validator_clock_and_negative_population(self):
        v,_=sample();a=classify(v,dict(status='PASS'),113,115)
        self.assertEqual(a['metrics']['validated_s'],15);self.assertEqual(a['completion_to_validator_s'],1)
        self.assertEqual(classify(v,dict(status='FAIL'),113,115)['outcome'],'WRONG_FINAL')
        for finish,outcome in [('length','OUTPUT_CAP'),('deadline','DEADLINE_CENSORED')]:
            x=copy.deepcopy(v);x['finish_reason']=finish
            a=classify(x,dict(status='PASS'),113,115)
            self.assertEqual(a['outcome'],outcome);self.assertIsNone(a['metrics']['validated_s'])
        with self.assertRaises(ValueError):classify(v,dict(status='VALIDATOR_ENV_ERROR'),113,115)
        with self.assertRaises(ValueError):classify(v,dict(status='PASS'),111,115)

    def test_pairs_different_valid_outputs_and_exact_population(self):
        rows=[row(1,'A'),row(2,'B',.8),row(3,'B',.9),row(4,'A')]
        rows[1]['observation']['native_output_ids']=[4,200002]
        out=paired(rows);self.assertEqual(out['status'],'GO_CLASS_UTILITY_SCREEN')
        self.assertAlmostEqual(out['median_paired_gain_percent']['first_final_s'],15)
        for transform in (lambda x:x.pop(),lambda x:x[2].update(profile='A'),lambda x:x[2].update(id='2'),lambda x:x[1]['assessment']['metrics'].update(first_final_s=float('nan')),lambda x:x[1]['observation'].update(official_input_ids=[]),lambda x:x[1]['observation']['initial'].update(n_calls=10)):
            x=copy.deepcopy(rows);transform(x)
            with self.assertRaises(ValueError):paired(x)

    def test_no_false_gain_fast_wrong_or_both_failed(self):
        for a,b in [(True,False),(False,True),(False,False)]:
            rows=[row(1,'A',1,a),row(2,'B',.01,b),row(3,'B',.01,b),row(4,'A',1,a)]
            out=paired(rows);self.assertEqual(out['status'],'NO_GO_CLASS_UTILITY_SCREEN');self.assertEqual(len(out['population']),4)
            self.assertIsNone(out['median_paired_gain_percent']['first_final_s'])
        rows=[row(1,'A'),row(2,'B',.8),row(3,'B',.8),row(4,'A')]
        rows[1]['assessment']['metrics']['completion_s']=20
        self.assertEqual(paired(rows)['status'],'NO_GO_CLASS_UTILITY_SCREEN')


if __name__=='__main__':unittest.main()
