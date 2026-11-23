"""Discriminating C152 journal gates, including legal retrospective worker tails."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from c152_journal_validate import validate,HEADER


def event(kind,when,**kw):
    e=dict(zip(HEADER,[kind,0,when,0,7,3,-1,0,-1,-1,0,1,9,-1,1]));e.update(kw);return e

def call(kind,when,cid):return event(kind,when,layer=-1,expert=2044+cid-1,slot=2044+cid-1,n_tokens=1,call_id=cid,generation=0,work_id=0)

def load():
    out=[event('LOAD_BEGIN',111,logical_bytes=64)]
    for j,(ra,rb,sa,sb,size) in enumerate(((112,114,115,117,16),(118,120,121,123,16),(124,126,127,139,32))):
        for kind,t in (('READ_BEGIN',ra),('READ_END',rb),('TENSOR_SET_BEGIN',sa),('TENSOR_SET_RETURN',sb)):
            out.append(event(kind,t,component=j,logical_bytes=size))
    return out+[event('LOAD_END',140,logical_bytes=64)]

def fixture(inherited=False,resident=False):
    first=[] if inherited else [call('CALL_BEGIN',100,1),event('ENQUEUE',101),event('DEQUEUE',110,component=0),call('CALL_END',115,1)]
    first += [call('CALL_BEGIN',116,2),event('BARRIER_SLOT',119,call_id=2,state=2 if resident else 1,work_id=0),event('WAIT_BEGIN',120,call_id=2,expert=-1,slot=-1,generation=0,work_id=0,n_tokens=1)]
    if not resident:first+=load()+[event('RESIDENT_COMMIT',145,state=2,component=0)]
    first += [event('WAIT_END',150,call_id=2,expert=-1,slot=-1,generation=0,work_id=0,n_tokens=1),call('CALL_END',160,2)]
    return first

def initial(resident=False):
    w={'layer':0,'expert':7,'slot':3,'generation':9,'origin_call':1,'enqueue_us':95,'work_id':1,'worker':0,'phase':1}
    return {'transition_seq':0,'queue':[],'owned':[] if resident else [w]}

class Journal(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.p=Path(self.t.name)/'journal.trace'
    def write(self,rows,metadata=None,overflow=0):
        text=['#c156-expert-snapshot-v2',*(metadata or ['L\t0\t64\tCPU']),f'R\t1\t0\t{len(rows)}','\t'.join(HEADER)]
        for i,e in enumerate(rows):e['seq']=i;text.append('\t'.join(str(e[k]) for k in HEADER))
        text.append(f'#end\t{len(rows)}\t{overflow}');self.p.write_text('\n'.join(text)+'\n')
    def gate(self,rows=None,**kw):
        self.write(fixture() if rows is None else rows);return validate(self.p,physical=False,**kw)
    def reject(self,rows):
        self.write(rows)
        with self.assertRaises(ValueError):validate(self.p,physical=False)
    def test_complete_async_cross_call_retrospective(self):
        d=self.gate();self.assertEqual(len(d['loads']),1);self.assertEqual(d['barriers'][0]['ready_us'],145)
        self.assertGreater(d['pairs']['LOAD_BEGIN'][0][1]['mono_us'],d['calls'][1]['end']['mono_us'])
        self.assertLess(d['pairs']['LOAD_BEGIN'][0][0]['mono_us'],d['rows'][6]['mono_us'])
    def test_inherited_loading_and_previous_origin_no_fake_enqueue(self):
        d=self.gate(fixture(inherited=True),initial=initial());self.assertEqual(list(d['commits']),[1])
    def test_initial_resident_needs_no_commit(self):
        d=self.gate(fixture(inherited=True,resident=True),initial=initial(True));self.assertFalse(d['barriers'][0]['blocking_commits'])
    def test_inherited_missing_snapshot_not_accepted(self):self.reject(fixture(inherited=True))
    def test_kinds_metadata_cardinality_overflow_truncation(self):
        for field,value in (('kind','ALIEN'),('work_id',0),('generation',0),('layer',36),('expert',128),('logical_bytes',-1)):
            r=fixture();r[1][field]=value;self.reject(r)
        for metadata in (['L\t0\t64\tCPU','L\t0\t64\tCPU'],['L\t0\t64\tCUDA0'],['ALIEN\t0'],['L\t0\t0\tCPU']):
            self.write(fixture(),metadata)
            with self.assertRaises(ValueError):validate(self.p,physical=False)
        self.write(fixture(),overflow=1)
        with self.assertRaises(ValueError):validate(self.p,physical=False)
        self.write(fixture());self.p.write_text(self.p.read_text().rsplit('\n',2)[0]+'\n')
        with self.assertRaises(ValueError):validate(self.p,physical=False)
    def test_bijection_component_and_work_identity(self):
        for kind in ('READ_BEGIN','LOAD_BEGIN','CALL_END','RESIDENT_COMMIT'):
            r=fixture();r.pop(next(i for i,e in enumerate(r) if e['kind']==kind));self.reject(r)
        for kind in ('READ_END','LOAD_END','RESIDENT_COMMIT','DEQUEUE','ENQUEUE'):
            r=fixture();i=next(i for i,e in enumerate(r) if e['kind']==kind);r.insert(i+1,deepcopy(r[i]));self.reject(r)
        for field in ('call_id','layer','expert','slot','generation','component','work_id'):
            r=fixture();e=next(e for e in r if e['kind']=='READ_END');e[field]+=1;self.reject(r)
    def test_component_containment_and_chronology(self):
        for kind,when in (('READ_BEGIN',110),('READ_END',150),('TENSOR_SET_BEGIN',110),('RESIDENT_COMMIT',139)):
            r=fixture();next(e for e in r if e['kind']==kind)['mono_us']=when;self.reject(r)
        r=fixture();next(e for e in r if e['kind']=='READ_END')['logical_bytes']=63;self.reject(r)
    def test_sync_containment_calls_and_pair_metadata(self):
        r=fixture();r[-1]['mono_us']=149;self.reject(r)
        r=fixture();r[4]['mono_us']=114;self.reject(r)
        r=fixture();r[-1]['n_tokens']=2;self.reject(r)
        r=fixture();r[5]['state']=3;self.reject(r)
    def test_barrier_exact_generation_and_missing_commit(self):
        for field,value in (('generation',10),('expert',8),('slot',4)):
            r=fixture();r[5][field]=value;self.reject(r)
        r=fixture();r.insert(6,deepcopy(r[5]));self.reject(r)
        r=fixture();next(e for e in r if e['kind']=='RESIDENT_COMMIT')['component']=1;self.reject(r)
    def test_stale_duplicate_and_cancelled_pending_work(self):
        r=fixture();r.insert(2,event('ENQUEUE',102,work_id=2));r.insert(4,event('STALE_WORK',113,work_id=2,component=1))
        d=self.gate(r);self.assertEqual(d['queue_tail_work_ids'],[])
        r=fixture();r.insert(2,event('ENQUEUE',102,work_id=2));r.append(event('CANCEL_WORK',165,work_id=2))
        d=self.gate(r);self.assertEqual(d['cancelled_work_ids'],[2])
        r.append(deepcopy(r[-1]));self.reject(r)
    def test_incomplete_name_and_size(self):
        self.write(fixture());partial=self.p.with_suffix('.partial');partial.write_bytes(self.p.read_bytes())
        with self.assertRaises(ValueError):validate(partial,physical=False)
        with self.assertRaises(ValueError):validate(self.p,physical=False,max_bytes=10)
    def test_request_range_missing_or_crossed(self):
        self.write(fixture());s=self.p.read_text().replace('R\t1\t0\t','R\t1\t1\t');self.p.write_text(s)
        with self.assertRaises(ValueError):validate(self.p,physical=False)

if __name__=='__main__':unittest.main()
