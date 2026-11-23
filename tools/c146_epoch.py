"""Append-only accounting for the owner-authorized post-C145 epoch."""
from datetime import datetime, timezone
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
EPOCH = ROOT/'results/c146-post-c145-resume-20260930T011645Z'

def now():
    return {'utc':datetime.now(timezone.utc).isoformat(),'monotonic_s':time.monotonic()}

def record(unit, start, end, *, live, status, paths=(), worst_case_s=None):
    elapsed=end['monotonic_s']-start['monotonic_s']
    if elapsed<0:raise ValueError('negative unit envelope')
    row={'unit':unit,'start':start,'end':end,'elapsed_s':elapsed,
         'physical_charge_s':elapsed if live else 0,'live':live,'status':status,
         'evidence_paths':list(map(str,paths)),'worst_case_s':worst_case_s}
    with (EPOCH/'ledger.jsonl').open('a') as f:
        f.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n');f.flush()
    return row

def budget(worst_case_s=0, raw_projection=0):
    epoch=json.loads((EPOCH/'epoch.json').read_text())
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=epoch['boot_id']:
        raise ValueError('boot changed; epoch clock must be reconciled')
    rows=[json.loads(line) for line in (EPOCH/'ledger.jsonl').read_text().splitlines()]
    live=sorted((r['start']['monotonic_s'],r['end']['monotonic_s']) for r in rows if r['live'])
    spent=0;finish=None
    for a,b in live:
        spent+=max(0,b-max(a,finish if finish is not None else a));finish=max(b,finish or b)
    wall=time.monotonic()-epoch['start_monotonic_s']
    raw=sum(p.stat().st_size for p in ROOT.glob('results/c*/raw/**/*') if p.is_file()
            and any(x in str(p.relative_to(ROOT)) for x in ('c147-','c147b-','c148-','c149-','c150-','c151-','c152-','c153-','c154-','c155-','c156-')))
    reserve=epoch['physical_closure_reserve_s']
    out={'utc':now()['utc'],'physical_used_s':spent,'wall_used_s':wall,'raw_bytes':raw,
         'physical_remaining_s':epoch['physical_limit_s']-spent,'wall_remaining_s':epoch['wall_limit_s']-wall,
         'raw_remaining_bytes':epoch['raw_limit_bytes']-raw,'closure_reserve_s':reserve,
         'next_worst_case_s':worst_case_s,'admitted':spent+worst_case_s+reserve<=epoch['physical_limit_s']
         and wall+worst_case_s+reserve<=epoch['wall_limit_s'] and raw+raw_projection<=epoch['raw_limit_bytes']}
    return out
