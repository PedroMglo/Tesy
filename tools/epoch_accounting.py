"""Append-only live envelopes and admission for an explicitly authorized epoch."""
from datetime import datetime, timezone
import json
from pathlib import Path
import time

def now():
    return {'utc':datetime.now(timezone.utc).isoformat(),'monotonic_s':time.monotonic()}

class Epoch:
    def __init__(self,path):
        self.path=Path(path).resolve();self.root=self.path.parents[1]
        self.config=json.loads((self.path/'epoch.json').read_text())
        if Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=self.config['boot_id']:
            raise ValueError('boot changed; clock reconciliation required')
    def record(self,unit,start,end,*,live,status,paths=(),worst_case_s=None):
        elapsed=end['monotonic_s']-start['monotonic_s']
        if elapsed<0:raise ValueError('negative envelope')
        row={'unit':unit,'start':start,'end':end,'elapsed_s':elapsed,'live':live,
             'physical_charge_s':elapsed if live else 0,'status':status,
             'evidence_paths':list(map(str,paths)),'worst_case_s':worst_case_s}
        with (self.path/'ledger.jsonl').open('a') as f:
            f.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n');f.flush()
        return row
    def budget(self,worst_case_s=0,raw_projection=0):
        if worst_case_s<0 or raw_projection<0:raise ValueError('negative admission')
        rows=[json.loads(x) for x in (self.path/'ledger.jsonl').read_text().splitlines()]
        intervals=sorted((r['start']['monotonic_s'],r['end']['monotonic_s']) for r in rows if r['live'] and r['start'] is not None and r['end'] is not None)
        spent=0;finish=None
        for a,b in intervals:
            spent+=max(0,b-max(a,a if finish is None else finish));finish=max(b,b if finish is None else finish)
        # Charges without observed endpoint timestamps cannot receive overlap credit.
        spent += sum(r['physical_charge_s'] for r in rows if r['live'] and (r['start'] is None or r['end'] is None))
        wall=time.monotonic()-self.config['start_monotonic_s']
        names=list(self.config.get('raw_roots',[]))
        addendum=self.path/'raw-roots-addendum.json'
        if addendum.exists():
            extra=json.loads(addendum.read_text())
            if set(extra)!={'effective_raw_roots','reason'} or type(extra['effective_raw_roots']) is not list:
                raise ValueError('raw root addendum schema invalid')
            names+=extra['effective_raw_roots']
        transition=self.path/'raw-root-transition.json'
        if transition.exists():
            extra=json.loads(transition.read_text())
            if set(extra)!={'previous_addendum_sha256','append_roots','reason'} or type(extra['append_roots']) is not list:
                raise ValueError('raw root transition schema invalid')
            import hashlib
            if hashlib.sha256(addendum.read_bytes()).hexdigest()!=extra['previous_addendum_sha256']:
                raise ValueError('raw root transition parent changed')
            names+=extra['append_roots']
        roots=[]
        for name in dict.fromkeys(names):
            p=(self.root/name).resolve()
            if not p.is_relative_to(self.root/'results') or p.name!='raw':raise ValueError('raw root outside declared results/raw')
            roots.append(p)
        raw=sum(p.stat().st_size for d in roots for p in d.rglob('*') if p.is_file())
        reserve=self.config['closure_reserve_s']
        wall_reserve=self.config.get('wall_closure_reserve_s',reserve)
        out={'utc':now()['utc'],'physical_used_s':spent,'wall_used_s':wall,'raw_bytes':raw,
             'physical_remaining_s':self.config['physical_limit_s']-spent,
             'wall_remaining_s':self.config['wall_limit_s']-wall,
             'raw_remaining_bytes':self.config['raw_limit_bytes']-raw,'closure_reserve_s':reserve,
             'next_worst_case_s':worst_case_s}
        out['admitted']=not (self.path/'closure.json').exists() and all((
            spent+worst_case_s+reserve<=self.config['physical_limit_s'],
            wall+worst_case_s+wall_reserve<=self.config['wall_limit_s'],
            raw+raw_projection<=self.config['raw_limit_bytes']))
        return out
