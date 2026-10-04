"""Append-only live envelopes and admission for an explicitly authorized epoch."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time

def now():
    return {'utc':datetime.now(timezone.utc).isoformat(),'monotonic_s':time.monotonic()}

class Epoch:
    def __init__(self,path):
        self.path=Path(path).resolve();self.root=self.path.parents[1]
        self.config=json.loads((self.path/'epoch.json').read_text())
        self.boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        if self.boot_id!=self.config['boot_id'] and self.config.get('wall_accounting')!='active-v1':
            raise ValueError('boot changed; clock reconciliation required')
    def record(self,unit,start,end,*,live,status,paths=(),worst_case_s=None):
        elapsed=end['monotonic_s']-start['monotonic_s']
        if elapsed<0:raise ValueError('negative envelope')
        row={'unit':unit,'start':start,'end':end,'elapsed_s':elapsed,'live':live,
             'physical_charge_s':elapsed if live else 0,'status':status,
             'evidence_paths':list(map(str,paths)),'worst_case_s':worst_case_s}
        if self.config.get('wall_accounting')=='active-v1':row['boot_id']=self.boot_id
        with (self.path/'ledger.jsonl').open('a') as f:
            f.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n');f.flush()
        return row
    def budget(self,worst_case_s=0,raw_projection=0):
        if worst_case_s<0 or raw_projection<0:raise ValueError('negative admission')
        rows=[json.loads(x) for x in (self.path/'ledger.jsonl').read_text().splitlines()]
        intervals=sorted((r.get('boot_id',self.config['boot_id']),r['start']['monotonic_s'],r['end']['monotonic_s']) for r in rows if r['live'] and r['start'] is not None and r['end'] is not None)
        spent=0;finish=None;boot=None
        for identity,a,b in intervals:
            if identity!=boot:finish=None;boot=identity
            spent+=max(0,b-max(a,a if finish is None else finish));finish=max(b,b if finish is None else finish)
        # Charges without observed endpoint timestamps cannot receive overlap credit.
        spent += sum(r['physical_charge_s'] for r in rows if r['live'] and (r['start'] is None or r['end'] is None))
        wall=time.monotonic()-self.config['start_monotonic_s']
        calendar_ok=True
        if self.config.get('wall_accounting')=='active-v1':
            wall=self.active_wall()
            calendar_ok=datetime.now(timezone.utc)<datetime.fromisoformat(self.config['deadline_utc'])
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
            calendar_ok,
            spent+worst_case_s+reserve<=self.config['physical_limit_s'],
            wall+worst_case_s+wall_reserve<=self.config['wall_limit_s'],
            raw+raw_projection<=self.config['raw_limit_bytes']))
        return out

    def active_wall(self):
        """Prospective active research clock; legacy epochs retain elapsed wall.

        Completed sessions are append-only. An open session conservatively charges
        all elapsed time, including builds/waits. After reboot, explicit clock
        reconciliation is required rather than subtracting an invented idle gap.
        """
        rows=[json.loads(x) for x in (self.path/'active-wall.jsonl').read_text().splitlines()]
        total=0;last={}
        for row in rows:
            a,b=row['start_monotonic_s'],row['end_monotonic_s']
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in (a,b)) or b<a:
                raise ValueError('invalid active research span')
            boot=row['boot_id']
            if a<last.get(boot,-1):raise ValueError('overlapping active research sessions')
            last[boot]=b;total+=b-a
        session=json.loads((self.path/'active-session.json').read_text())
        if session is not None:
            if session['boot_id']!=self.boot_id:raise ValueError('open research session crossed reboot; reconcile conservatively first')
            start=session['start_monotonic_s'];end=time.monotonic()
            if not math.isfinite(start) or start<last.get(self.boot_id,-1) or end<start:
                raise ValueError('invalid open active research session')
            total+=end-start
        return total
