import copy,unittest
from expert_staging_product_cost_gate import evaluate,validate_runs

def rows(prefill=10.,decode=20.):
    initial=dict(layers=[],pending_queue=0,n_calls=10)
    return [dict(trace=False,staging_enabled=on,native_argmax_ids=[1,2],initial=copy.deepcopy(initial),final=copy.deepcopy(initial),prefix_s=10.,prefill153_s=prefill if on else 10.,decode32_s=decode if on else 20.,total_s=prefill+decode if on else 30.,stage_stats={}) for on in (False,True,True,False)]

class ProductCost(unittest.TestCase):
    def test_actual_environment_absence_boundary(self):
        runs=[dict(id=f'{c}-{i}',case=c,stage=on,trace=False,env={'TESY_C296_ESTIMATOR':'1','TESY_C305_STAGE':'1'} if on else {},command=['binary','model','fixture',c,f'root-{c}-{i}','R0','v1']) for c in ('nominal153','code153') for i,on in enumerate((False,True,True,False))]
        validate_runs(runs)
        for bad in [{'TESY_C296_ESTIMATOR':'0'},{'TESY_C305_STAGE':'0'},{'TESY_C294_WINDOW':'1'}]:
            r=copy.deepcopy(runs);r[0]['env']=bad
            with self.assertRaises(ValueError):validate_runs(r)
    def test_global_and_phase_thresholds(self):
        self.assertEqual(evaluate(dict(nominal153=rows(10,16),code153=rows()))['status'],'GO_REAL_STAGING_INTEGRATED_COST')
        self.assertEqual(evaluate(dict(nominal153=rows(8.9,20),code153=rows()))['status'],'PHASE_SURVIVOR_REAL_STAGING_COST')
        self.assertEqual(evaluate(dict(nominal153=rows(10,19),code153=rows()))['status'],'NO_GO_REAL_STAGING_INTEGRATED_COST')
    def test_other_case_protected(self):
        self.assertEqual(evaluate(dict(nominal153=rows(10,16),code153=rows(10,23)))['status'],'NO_GO_REAL_STAGING_INTEGRATED_COST')
    def test_two_positive_pairs_required(self):
        r=rows(10,10);r[2].update(decode32_s=20.1,total_s=30.1)
        self.assertEqual(evaluate(dict(nominal153=r,code153=rows()))['status'],'NO_GO_REAL_STAGING_INTEGRATED_COST')
    def test_cardinality_order_profile(self):
        for a in [[],rows()[:3]]:
            with self.assertRaises(ValueError):evaluate(dict(nominal153=a,code153=rows()))
        r=rows();r[1]['staging_enabled']=False
        with self.assertRaises(ValueError):evaluate(dict(nominal153=r,code153=rows()))
        with self.assertRaises(ValueError):evaluate(dict(nominal153=rows()))
    def test_no_missing_nonfinite_or_zero_scores(self):
        for v in [0.,float('nan'),float('inf'),None]:
            r=rows();r[1]['decode32_s']=v
            with self.assertRaises(ValueError):evaluate(dict(nominal153=r,code153=rows()))
    def test_initial_state_and_native_id_mismatch(self):
        for k,v in [('native_argmax_ids',[1,3]),('initial',dict(layers=[],pending_queue=0,n_calls=11))]:
            r=rows();r[1][k]=v
            with self.assertRaises(ValueError):evaluate(dict(nominal153=r,code153=rows()))

if __name__=='__main__':unittest.main()
