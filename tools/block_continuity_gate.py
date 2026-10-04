"""Validate full native multigrid payloads, identity and witnessed cancellation."""
import argparse
import json
import math
from pathlib import Path
import struct
from c94_session_wave_8k_reference import tree_digest


def inspect(root,fixture,case,B):
    root=Path(root);spec=json.loads(Path(fixture).read_text())[case];out=json.loads((root/'result.json').read_text())
    if out.get('status')!='PASS_SELECTED_MULTIGRID_R1_AND_NATIVE_CANCEL' or out.get('B')!=B or out.get('case')!=case or out.get('official_prefix_ids')!=spec['ids'] or out.get('native_continuation_ids')!=spec['continuation_ids'][:3*B]:
        raise ValueError('continuity official inputs/profile/complete receipt invalid')
    checks=out.get('checks',[])
    if len(checks)!=3*B or [(x['grid'],x['known']) for x in checks]!=[(g,k) for g in range(3) for k in range(1,B+1)]:
        raise ValueError('missing/duplicate multigrid positions')
    if out.get('abort_rc')!=2 or not out.get('abort_callback_calls',0)>0 or out.get('cancel_then_clean_full_logits_bitwise') is not True:
        raise ValueError('actual native cancellation/clean continuation missing')
    all_data=[]
    for g in range(3):
        data=(root/f'grid-{g}.base.f32').read_bytes()
        if len(data)!=B*201088*4:raise ValueError('incomplete full-grid logits')
        all_data.append(data)
        for row in checks[g*B:(g+1)*B]:
            k=row['known'];actual=spec['continuation_ids'][g*B:g*B+k]+[0]*(B-k)
            if row['position']!=len(spec['ids'])+g*B or row['inputs']!=actual or row['fixed_padding']!=0 or row['complete_preceding_rows_bitwise'] is not True:
                raise ValueError('reference not fixed confirmed prefix')
            ref=(root/f'grid-{g}.known-{k}.f32').read_bytes();all_data.append(ref)
            if len(ref)!=len(data) or ref[:k*201088*4]!=data[:k*201088*4]:raise ValueError('native prefix/rollback discrepancy')
    if not all(math.isfinite(x[0]) for d in all_data for x in struct.iter_unpack('<f',d)):
        raise ValueError('nonfinite native reference')
    return dict(status='PASS_SELECTED_NATIVE_MULTIGRID_R1_CANCEL',case=case,B=B,grids=3,queries=3*B,finite=True,raw_tree=tree_digest(root),scope=out['scope'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('fixture',type=Path);p.add_argument('case');p.add_argument('B',type=int);a=p.parse_args()
    result=inspect(a.root,a.fixture,a.case,a.B)
    with (a.root.parent/(a.root.name+'.continuity-summary.json')).open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(result))
