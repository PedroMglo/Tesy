import copy,unittest
from expert_staging_cost_gate import observer,metrics

def rows():
    return [dict(trace=t,staging_enabled=True,native_argmax_ids=[1,2],initial=dict(layers=[],pending_queue=0,n_calls=10),prefix_s=10.,prefill153_s=10.2 if t else 10.,decode32_s=20.4 if t else 20.,total_s=30.6 if t else 30.) for t in [False,True,True,False]]
class Observer(unittest.TestCase):
    def test_fixed_paired_percentages(self):
        v=observer(dict(nominal153=rows(),code153=rows()));self.assertTrue(v['cases']['nominal153']['neutral_timing']);self.assertAlmostEqual(v['cases']['nominal153']['median_overhead_percent']['decode32_s'],2)
    def test_empty_wrong_order_or_missing_case(self):
        for data in [{},{'nominal153':rows()},{'nominal153':[],'code153':rows()},{'nominal153':list(reversed(rows()[:3])),'code153':rows()}]:
            with self.assertRaises(ValueError):observer(data)
    def test_initial_state_or_sameprofile_ids_mismatch(self):
        for field,value in [('native_argmax_ids',[1,3]),('initial',dict(layers=[],pending_queue=0,n_calls=11))]:
            r=rows();r[1][field]=value
            with self.assertRaises(ValueError):observer(dict(nominal153=r,code153=rows()))
    def test_expensive_observer_kept_diagnostic(self):
        r=rows()
        for v in r:
            if v['trace']:v['decode32_s']=25.
        out=observer(dict(nominal153=r,code153=r));self.assertFalse(out['cases']['nominal153']['neutral_timing'])
    def test_cleanup_not_subtracted_missing_nan_rejected(self):
        metrics(dict(stage_cleanup_s=.01,decode_forward_s=1.,decode32_s=1.01))
        for v in [dict(stage_cleanup_s=.01,decode_forward_s=1.,decode32_s=1.),dict(stage_cleanup_s=float('nan'),decode_forward_s=1.,decode32_s=1.),dict(decode_forward_s=1.,decode32_s=1.)]:
            with self.assertRaises(ValueError):metrics(v)
if __name__=='__main__':unittest.main()
