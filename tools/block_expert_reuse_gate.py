"""Selected CPU FFN reuse: exact numeric receipts and actual native loads."""
import argparse
import json
import math
from pathlib import Path

PHASES = ['prefill0', 'prefill128', 'prefill_final']
TOKENS = [32, 32, 29]
UNIONS = {0: (79, 171), 12: (64, 114), 24: (68, 134)}


def inspect(value, layer, mode):
    if layer not in UNIONS or mode not in ('numeric-A', 'numeric-B', 'timing-A', 'timing-B'):
        raise ValueError('unfrozen selected layer/mode')
    numeric = mode.startswith('numeric')
    candidate = mode.endswith('B')
    expected = 'PASS_SELECTED_REUSE_NUMERIC' if numeric else 'MEASURED_SELECTED_REUSE_SERVICE'
    if (value.get('status') != expected or value.get('mode') != mode or type(value.get('layer')) is not int or value.get('layer') != layer
            or value.get('slots') != 40 or value.get('threads') != 8 or value.get('wave_capacity') != 18
            or value.get('original_tile_shapes') != TOKENS
            or value.get('groups') != ([93] if candidate else TOKENS)
            or value.get('waves_by_group') != ([8] if candidate else [8, 8, 7])):
        raise ValueError('wrong operator/profile/groups/tile boundary')
    if value.get('direct_reader') is not True or value.get('logical_bytes_not_NVMe_traffic') is not True:
        raise ValueError('direct reader/byte convention absent')
    outputs = value.get('outputs')
    if not isinstance(outputs, list) or len(outputs) != 3:
        raise ValueError('missing/duplicate native tile outputs')
    for result, phase, tokens in zip(outputs, PHASES, TOKENS):
        if (result.get('phase') != phase or result.get('tokens') != tokens
                or result.get('bitwise') is not True or type(result.get('nonfinite')) is not int or result.get('nonfinite') != 0
                or type(result.get('max_abs')) not in (int, float)
                or not math.isfinite(result['max_abs']) or result['max_abs'] != 0):
            raise ValueError('native canonical per-tile reference invalid')
    expected_witness = UNIONS[layer][0 if candidate else 1] if numeric else 0
    if value.get('consumer_byte_combinations') != expected_witness:
        raise ValueError('all active expert consumer byte witnesses required outside timing')
    wall = value.get('service_wall_s')
    if type(wall) not in (int, float) or not math.isfinite(wall) or wall <= 0:
        raise ValueError('missing/nonfinite/zero native service time')
    states = [value.get('initial'), value.get('final')]
    for state in states:
        if not isinstance(state, dict) or state.get('logical_bytes_per_load') != 13219200:
            raise ValueError('missing original logical load byte accounting')
        for name in ('slot_expert', 'slot_state', 'slot_generation'):
            if not isinstance(state.get(name), list) or len(state[name]) != 40:
                raise ValueError('incomplete per-slot state')
        if any(type(x) is not int or x < 0 for x in state['slot_generation']):
            raise ValueError('invalid generation')
        if any(type(x) is not int or x not in (0, 2) for x in state['slot_state']):
            raise ValueError('workers not drained or invalid state')
        if any(type(x) is not int or not -1 <= x < 128 for x in state['slot_expert']):
            raise ValueError('invalid logical expert')
        resident = []
        for expert, status, generation in zip(state['slot_expert'], state['slot_state'], state['slot_generation']):
            if status == 2:
                if expert < 0 or generation <= 0:
                    raise ValueError('resident expert/generation absent')
                resident.append(expert)
            elif expert != -1 or generation != 0:
                raise ValueError('empty-slot metadata inconsistent')
        if len(resident) != len(set(resident)):
            raise ValueError('logical expert duplicated in resident slots')
        for name in ('demand_loads', 'preload_loads', 'waves', 'wait_union_us', 'cache_bytes'):
            if type(state.get(name)) is not int or state[name] < 0:
                raise ValueError('invalid native counter/accounting')
    initial, final = states
    if any(initial['slot_generation']) or any(x != -1 for x in initial['slot_expert']) or any(initial['slot_state']):
        raise ValueError('initial pool is not the frozen empty native state')
    if any(initial[k] != 0 for k in ('demand_loads', 'preload_loads', 'waves', 'wait_union_us')):
        raise ValueError('unrecorded earlier native work')
    if initial['cache_bytes'] != final['cache_bytes'] or initial['cache_bytes'] < 528768000:
        raise ValueError('native equal-capacity pool changed')
    loads = final['demand_loads'] + final['preload_loads']
    if loads != sum(final['slot_generation']):
        raise ValueError('logical loads do not match actual native reservations')
    union, independent_upper = UNIONS[layer]
    if not union <= loads <= independent_upper or candidate and loads != union:
        raise ValueError('actual union service/load elimination not demonstrated')
    return {'status': expected, 'layer': layer, 'mode': mode,
            'service_wall_s': wall, 'actual_loads': loads,
            'logical_loaded_bytes': loads * 13219200,
            'actual_demand_loads': final['demand_loads'],
            'actual_preload_loads': final['preload_loads'],
            'wait_union_s': final['wait_union_us'] / 1e6,
            'witness_components': 6 * expected_witness,
            'scope': 'Selected disjoint CPU tiles with empty layer pool; no server/prefill speedup or physical NVMe traffic claim'}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('receipt', type=Path)
    p.add_argument('--layer', type=int)
    p.add_argument('--mode')
    p.add_argument('--output', type=Path)
    p.add_argument('--numeric-family', action='store_true')
    a = p.parse_args()
    if a.numeric_family:
        protocol = json.loads((a.receipt / 'protocol.json').read_text())
        rows = []
        if [(r['layer'], r['mode']) for r in protocol['runs']] != [(layer, mode) for layer in (0, 12, 24) for mode in ('numeric-A', 'numeric-B')]:
            raise ValueError('exact numeric layer/control-candidate order required')
        for run in protocol['runs']:
            path = a.receipt / 'raw' / (run['id'] + '.operator.json')
            rows.append(inspect(json.loads(path.read_text()), run['layer'], run['mode']))
        result = {'status': 'PASS_SELECTED_REUSE_NUMERIC_FAMILY', 'arms': rows,
                  'scope': 'Original native/canonical CPU FFN references and consumer bytes; operator timing, full prefill and utility NOT_RUN'}
        a.output = a.receipt / 'numeric-summary.json'
    else:
        if a.layer is None or a.mode is None or a.output is None:
            raise ValueError('explicit layer/mode/output required')
        result = inspect(json.loads(a.receipt.read_text()), a.layer, a.mode)
    with a.output.open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
        f.write('\n')
    print(json.dumps(result))
