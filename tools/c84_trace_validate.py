#!/usr/bin/env python3
"""Validate a bounded C84 diagnostic trace before any demand/cache analysis."""

import argparse
from pathlib import Path

from c2_gate import GateError

HEADER = ('kind', 'seq', 'mono_us', 'layer', 'expert', 'slot', 'victim',
          'n_tokens', 'wave', 'state', 'logical_bytes')
KINDS = {'DEMAND', 'EVICT', 'RESERVE', 'PRELOAD', 'LOAD_BEGIN',
         'LOAD_END', 'LOAD_ERROR', 'WAIT_BEGIN', 'WAIT_END'}
EXPERT_BYTES = 13_219_200


def integer(value, name, lo=None, hi=None):
    if not value or value.strip() != value or value.startswith('+'):
        raise GateError(f'invalid C84 {name}')
    try:
        number = int(value)
    except ValueError as error:
        raise GateError(f'invalid C84 {name}') from error
    if str(number) != value or (lo is not None and number < lo) or \
       (hi is not None and number > hi):
        raise GateError(f'C84 {name} out of range')
    return number


def validate(path, expected_layers=36, expected_expert_bytes=EXPERT_BYTES):
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= 64 * 2**20:
        raise GateError('C84 trace missing/oversize/empty')
    with path.open(newline='') as stream:
        if stream.readline() != '#c84-expert-demand-v1\n' or \
           stream.readline() != '#layer\tlayer\tlogical_expert_bytes\tbuffer_name\n':
            raise GateError('C84 trace header mismatch')
        layers = {}
        line = stream.readline()
        while line.startswith('L\t'):
            parts = line.rstrip('\n').split('\t')
            if len(parts) != 4:
                raise GateError('C84 layer row malformed')
            layer = integer(parts[1], 'layer', 0, 35)
            size = integer(parts[2], 'expert bytes', 1)
            if layer in layers or size != expected_expert_bytes or not parts[3] or \
               parts[3] == 'UNALLOCATED':
                raise GateError('C84 layer identity/size invalid')
            layers[layer] = {'logical_expert_bytes': size, 'buffer_name': parts[3]}
            line = stream.readline()
        if set(layers) != set(range(expected_layers)) or line.rstrip('\n').split('\t') != list(HEADER):
            raise GateError('C84 layer/header coverage invalid')
        rows = []
        footer = None
        for line in stream:
            if line.startswith('#end\t'):
                if footer is not None:
                    raise GateError('duplicate C84 footer')
                footer = line.rstrip('\n').split('\t')
                if stream.read():
                    raise GateError('C84 trailing data')
                break
            if len(rows) >= 300000:
                raise GateError('C84 trace event cap exceeded')
            parts = line.rstrip('\n').split('\t')
            if len(parts) != len(HEADER) or parts[0] not in KINDS:
                raise GateError('C84 event schema invalid')
            row = {'kind': parts[0]}
            for key, value in zip(HEADER[1:], parts[1:]):
                row[key] = integer(value, key)
            if row['seq'] != len(rows) or row['mono_us'] <= 0 or \
               row['layer'] not in layers or row['expert'] < -1 or row['expert'] >= 128 or \
               row['slot'] < -1 or row['slot'] >= 32 or row['victim'] < -1 or \
               row['victim'] >= 128 or row['n_tokens'] < 0 or row['n_tokens'] > 32 or \
               row['wave'] < -1 or row['wave'] > 32 or row['state'] < -1 or row['state'] > 2 or \
               row['logical_bytes'] < 0:
                raise GateError('C84 event value invalid')
            if row['kind'] == 'DEMAND' and (row['expert'] < 0 or row['n_tokens'] < 1 or
                                             row['state'] not in (0, 1, 2) or
                                             (row['state'] == 0) != (row['slot'] == -1)):
                raise GateError('C84 demand status invalid')
            if row['kind'] in ('LOAD_BEGIN', 'LOAD_END', 'LOAD_ERROR') and \
               (row['expert'] < 0 or row['slot'] < 0 or row['logical_bytes'] != expected_expert_bytes):
                raise GateError('C84 load identity/bytes invalid')
            rows.append(row)
        if footer is None or len(footer) != 3 or \
           integer(footer[1], 'footer count', 0) != len(rows) or \
           integer(footer[2], 'overflow', 0, 1) != 0:
            raise GateError('C84 trace incomplete/overflowed')
    if not rows or any(row['kind'] == 'LOAD_ERROR' for row in rows):
        raise GateError('C84 empty trace or load error')
    last_demand_time = -1
    load_count = 0
    wait_stack = {}
    for index, row in enumerate(rows):
        kind = row['kind']
        if kind == 'DEMAND':
            if row['mono_us'] < last_demand_time:
                raise GateError('C84 demand order inconsistent')
            last_demand_time = row['mono_us']
        if kind == 'LOAD_BEGIN':
            if index + 1 >= len(rows) or rows[index+1]['kind'] != 'LOAD_END' or \
               any(rows[index+1][key] != row[key] for key in ('layer','expert','slot','logical_bytes')) or \
               rows[index+1]['mono_us'] < row['mono_us']:
                raise GateError('C84 load pair incomplete')
            load_count += 1
        if kind in ('WAIT_BEGIN','WAIT_END'):
            key = (row['layer'], row['wave'])
            if kind == 'WAIT_BEGIN':
                if key in wait_stack:
                    raise GateError('C84 nested wait')
                wait_stack[key] = row['mono_us']
            elif key not in wait_stack or wait_stack.pop(key) > row['mono_us']:
                raise GateError('C84 unmatched wait')
    if wait_stack:
        raise GateError('C84 wait incomplete')
    return {'schema':'c84-trace-validation-v1', 'status':'PASS',
            'layer_count':len(layers), 'events':len(rows),
            'demand_events':sum(row['kind']=='DEMAND' for row in rows),
            'load_pairs':load_count,
            'wait_pairs':sum(row['kind']=='WAIT_BEGIN' for row in rows),
            'layers':layers}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    import json
    print(json.dumps(validate(args.path), sort_keys=True))


if __name__ == '__main__':
    main()
