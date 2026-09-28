"""Fresh-process wave ON equality across the C70 full active boundary."""
from pathlib import Path

from c2_gate import GateError
from c70_full_boundary_gate import inspect
import c7_boundary_gate as c7


def compare(first, repeat):
    a = inspect(Path(first), skip_on=True)
    b = inspect(Path(repeat), skip_on=True)
    if a['core'].keys() != b['core'].keys() or a['masks'].keys() != b['masks'].keys():
        raise GateError('C72 repeated state keys differ')
    mismatch = []
    for key in sorted(a['core']):
        if a['core'][key] != b['core'][key]:
            mismatch.append({'phase': key[0], 'layer': key[1], 'stage': key[2]})
    for key in sorted(a['masks']):
        if a['masks'][key] != b['masks'][key]:
            mismatch.append({'phase': key[0], 'layer': key[1], 'stage': 'wave_mask'})
    for phase in c7.LOGIT_PHASES:
        if a['logits'][phase] != b['logits'][phase]:
            mismatch.append({'phase': phase, 'stage': 'full_logits'})
    return {'schema': 'c72-wave-on-repeat-v1',
            'status': 'SAME_PROFILE_BITWISE_PASS' if not mismatch else 'FAIL_SAME_PROFILE_FIDELITY',
            'numeric_states': 250, 'masked_states': 2,
            'core_stage_comparisons': len(a['core']), 'full_logits': len(c7.LOGIT_PHASES),
            'first_sentinels': a['sentinels'], 'repeat_sentinels': b['sentinels'],
            'first_index_sha256': a['coverage']['index_sha256'],
            'repeat_index_sha256': b['coverage']['index_sha256'],
            'mismatch': mismatch}
