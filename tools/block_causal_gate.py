"""Fixed-B evidence boundary. Historical C127/C210 gates are unchanged."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import struct

from c70_full_boundary_gate import _index, _values
from c94_session_wave_8k_reference import tree_digest


def inspect(root, B):
    root = Path(root).resolve()
    observations = [json.loads(line) for line in (root/'observations.jsonl').read_text().splitlines()]
    if observations[-1].get('status') != 'PASS_SELECTED_FIXED_SHAPE_CAUSALITY':
        raise ValueError('incomplete/negative causal run')
    phases = [*(f'r0_{i}' for i in range(B)), 'block_base',
              *(name for i in range(1, B) for name in (f'suffix_{i}', f'rollback_{i}'))]
    rows = _index(root)
    groups = defaultdict(dict)
    for row in rows:
        phase, layer, stage = row['phase'], int(row['layer']), row['name']
        count = 1 if phase.startswith('r0_') else B
        if phase not in phases or not 0 <= layer < 36 or int(row['state_tokens']) != count:
            raise ValueError('capture position/shape coverage changed')
        if stage in groups[phase, layer]:
            raise ValueError('duplicate block stage')
        data = root/row['file']
        if not data.resolve().is_relative_to(root) or data.stat().st_size != int(row['bytes']):
            raise ValueError('missing/truncated payload')
        groups[phase, layer][stage] = row
    required = {'attn_post_norm', 'ffn_moe_logits',
                'ffn_moe_probs', 'ffn_moe_topk', 'ffn_moe_weights_softmax',
                'ffn_moe_topk_stream', 'ffn_moe_out'}
    if set(groups) != {(phase, layer) for phase in phases for layer in range(36)} or \
            any(not required <= set(stages) or set(stages)-required-{'ffn_moe_logits_biased'} for stages in groups.values()):
        raise ValueError('complete block layer/stage coverage missing')
    expected = set()
    for phase in phases:
        count = 1 if phase.startswith('r0_') else B
        logits = (root/(phase+'.logits.f32')).read_bytes()
        if len(logits) != 201088*count*4:
            raise ValueError('complete logits missing/truncated')
        import math
        if not all(math.isfinite(value[0]) for value in struct.iter_unpack('<f', logits)):
            raise ValueError('nonfinite logits')
        for layer in (0, 25, 29, 35):
            top, remap = (groups[phase, layer][name] for name in ('ffn_moe_topk', 'ffn_moe_topk_stream'))
            if top['type'] != 'i32' or remap['type'] != 'i32' or top['ne'] != f'4,{count},1,1' or top['ne'] != remap['ne']:
                raise ValueError('routing shape/namespace invalid')
            logical, slots = _values(root, top), _values(root, remap)
            if len(logical) != 4*count or len(slots) != len(logical):
                raise ValueError('routing cardinality invalid')
            for expert, slot in zip(logical, slots):
                if not 0 <= expert < 128 or not 0 <= slot < 40:
                    raise ValueError('routing/sentinel invalid')
                expected.add((phase, layer, 0, expert, slot))
    seen = {}; generation = defaultdict(set)
    with (root/'byte_checks.tsv').open() as stream:
        checks = list(csv.DictReader(stream, delimiter='\t'))
    for row in checks:
        base = (row['phase'], *(int(row[k]) for k in ('layer', 'wave', 'logical', 'slot')))
        tensor, gen, size = (int(row[k]) for k in ('tensor', 'generation', 'bytes'))
        key = (*base, tensor)
        if base not in expected or not 0 <= tensor < 6 or gen <= 0 or \
                size != (4406400 if tensor < 3 else 11520) or row['status'] != 'EQUAL' or key in seen:
            raise ValueError('witness duplicate/metadata/bytes invalid')
        seen[key] = gen; generation[base].add(gen)
    if set(seen) != {(*base, component) for base in expected for component in range(6)} or \
            any(len(values) != 1 for values in generation.values()):
        raise ValueError('consumer witness incomplete/stale')
    return dict(status='PASS_SELECTED_FIXED_B_CAUSALITY', B=B, K=B-1,
                layer_states=len(groups), phases=len(phases), witness_components=len(seen),
                full_logit_rows=sum(1 if p.startswith('r0_') else B for p in phases),
                raw_tree=tree_digest(root),
                scope='189 prefix selected native IDs, fixed B masked future and full-grid resubmission; no independent R1/FFN-reference/amortization promotion')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('root', type=Path); parser.add_argument('B', type=int)
    args = parser.parse_args(); out = inspect(args.root, args.B)
    with (args.root.parent/(args.root.name+'.summary.json')).open('x') as stream:
        json.dump(out, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps(out))
