import copy,unittest
from expert_staging_gate import validate_journal

def fixture():
    kinds=[1,2,6,3,7,11,8];events=[]
    for us,k in enumerate(kinds,1):events.append(dict(us=us,scope=1,ticket=1,generation=4 if k in (7,11) else 0,kind=k,call=1,layer=2,expert=7,slot=3 if k in (7,11) else -1,component=-1))
    stats={k:0 for k in ['issued','deduplicated','no_capacity','reads','completed_reads','logical_read_weight_bytes','expired_queued','expired_ready','expired_running','consumed','waits','errors','peak_running_spec','validation_claims','validation_components']}
    stats.update(issued=1,reads=1,completed_reads=1,logical_read_weight_bytes=13219200,consumed=1,peak_running_spec=1)
    return dict(enabled=True,idle=True,fd_O_DIRECT=True,DIO_memory_alignment=4096,DIO_offset_alignment=4096,arena_bytes=132300000,metadata_bytes=1000000,journal_capacity=24576,stats=stats,journal=events)
class Staging(unittest.TestCase):
    def test_actual_lifecycle(self):validate_journal(fixture(),{(1,2,7)},False)
    def test_missing_readiness_or_commit(self):
        for kind in (1,2,3,6,7,11,8):
            f=fixture();f['journal']=[e for e in f['journal'] if e['kind']!=kind]
            with self.assertRaises(ValueError):validate_journal(f,{(1,2,7)},False)
    def test_wrong_primary_generation_slot_or_expert(self):
        for key,value in [('generation',5),('slot',4),('expert',8),('call',2),('scope',2)]:
            f=fixture();f['journal'][-2][key]=value
            with self.assertRaises(ValueError):validate_journal(f,{(1,2,7)},False)
    def test_no_future_false_buffered_or_zero_evidence(self):
        for key,value in [('idle',False),('fd_O_DIRECT',False),('journal',[]),('arena_bytes',200000000)]:
            f=fixture();f[key]=value
            with self.assertRaises(ValueError):validate_journal(f,{(1,2,7)},False)
        with self.assertRaises(ValueError):validate_journal(fixture(),{(2,2,7)},False)
    def test_error_counter_nan_missing_or_unbounded(self):
        for key,value in [('errors',1),('reads',float('nan')),('peak_running_spec',4),('logical_read_weight_bytes',0)]:
            f=fixture();f['stats'][key]=value
            with self.assertRaises(ValueError):validate_journal(f,{(1,2,7)},False)
    def test_witness_not_inferred(self):
        with self.assertRaises(ValueError):validate_journal(fixture(),{(1,2,7)},True)
    def test_cancelled_running_cannot_be_consumed(self):
        f=fixture();ev=copy.deepcopy(f['journal'][2]);ev['kind']=5;f['journal'].insert(2,ev)
        with self.assertRaises(ValueError):validate_journal(f,{(1,2,7)},False)
if __name__=='__main__':unittest.main()
