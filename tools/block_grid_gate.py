"""Actual prefix-only production R1 evidence; optional observer neutrality."""
import argparse
import json
import math
from pathlib import Path
import struct

from c94_session_wave_8k_reference import tree_digest


def inspect(root, B, fixture, case, observer_reference=None):
    root=Path(root).resolve();out=json.loads((root/'result.json').read_text())
    inputs=json.loads(Path(fixture).read_text())[case]
    if out.get('status')!='PASS_SELECTED_DRAFT_INDEPENDENT_GRID' or out['case']!=case or out['B']!=B or out['mode']!='grid' or out['official_prefix_ids']!=inputs['ids']:
        raise ValueError('native reference identity/complete outcome invalid')
    checks=out.get('checks',[])
    if len(checks)!=B or [x['known_rows'] for x in checks]!=list(range(1,B+1)):
        raise ValueError('missing/duplicate prefix reference positions')
    base=(root/'production-base.logits.f32').read_bytes()
    if len(base)!=B*201088*4:raise ValueError('complete production logits missing')
    payloads=[base]
    for row in checks:
        known=row['known_rows'];expected=inputs['continuation_ids'][:known]+[0]*(B-known)
        if row['prefix_only_inputs']!=expected or row['fixed_padding']!=0 or not row['preceding_complete_rows_bitwise']:
            raise ValueError('reference depends on non-prefix/draft data')
        data=(root/f'prefix-only-{known}.logits.f32').read_bytes();payloads.append(data)
        if len(data)!=len(base) or data[:known*201088*4]!=base[:known*201088*4]:
            raise ValueError('prefix-only full rows disagree')
    if not all(math.isfinite(x[0]) for data in payloads for x in struct.iter_unpack('<f',data)):
        raise ValueError('nonfinite native production reference')
    neutral=None
    if observer_reference is not None:
        reference=Path(observer_reference).read_bytes()
        neutral=reference==base
        if not neutral:raise ValueError('production/observer full-logit neutrality blocked; diagnose before timing promotion')
    return dict(status='PASS_SELECTED_PRODUCTION_PREFIX_ONLY_REFERENCE',B=B,case=case,
                query_positions=B,full_logit_rows=B*(B+1),observer_bitwise=neutral,
                reference_contract='Fixed prefill, completed B-row grids, confirmed partial prefix then deterministic ID0 padding; replay partial grid on rejection. No draft future enters reference.',
                scope='Selected full-grid prefix; source causal contract and this finite coverage, not a universal proof or stochastic sampling claim',raw_tree=tree_digest(root))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('B',type=int);p.add_argument('fixture',type=Path);p.add_argument('case');p.add_argument('--observer-reference',type=Path)
    a=p.parse_args();out=inspect(a.root,a.B,a.fixture,a.case,a.observer_reference)
    with (a.root.parent/(a.root.name+'.grid-summary.json')).open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(out))
