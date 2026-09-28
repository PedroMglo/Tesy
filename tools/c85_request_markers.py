#!/usr/bin/env python3
"""Validate opt-in client CLOCK_MONOTONIC request windows for a future trace."""

from pathlib import Path

from c2_gate import GateError, strict_json


def validate(path, run_id, expected_ids, raw_results, *, require_complete=True):
    if type(run_id) is not str or not run_id or type(expected_ids) not in (list, tuple) or \
       not expected_ids or any(type(x) is not str or not x for x in expected_ids) or \
       len(set(expected_ids)) != len(expected_ids):
        raise GateError('invalid C85 frozen request identities')
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= 1024 * 1024:
        raise GateError('C85 request marker receipt absent/oversize')
    rows = [strict_json(line) for line in path.read_text().splitlines()]
    if not rows:
        raise GateError('C85 empty request marker receipt')
    pairs = []
    open_start = None
    prior_end = -1
    for row in rows:
        if type(row) is not dict or set(row) != {'schema', 'run_id', 'request_id', 'kind', 'mono_ns'} or \
           row['schema'] != 'c85-request-monotonic-v1' or row['run_id'] != run_id or \
           type(row['request_id']) is not str or type(row['mono_ns']) is not int or \
           row['mono_ns'] <= 0:
            raise GateError('C85 marker schema/identity invalid')
        if row['kind'] == 'REQUEST_START':
            if open_start is not None or len(pairs) >= len(expected_ids) or \
               row['request_id'] != expected_ids[len(pairs)] or row['mono_ns'] <= prior_end:
                raise GateError('C85 duplicate/out-of-order/overlapping request start')
            open_start = row
        elif row['kind'] == 'RESPONSE_COMPLETE':
            if open_start is None or row['request_id'] != open_start['request_id'] or \
               row['mono_ns'] <= open_start['mono_ns']:
                raise GateError('C85 unmatched response completion')
            pairs.append({'request_id':row['request_id'],
                          'request_start_ns':open_start['mono_ns'],
                          'response_complete_ns':row['mono_ns']})
            prior_end = row['mono_ns']
            open_start = None
        else:
            raise GateError('C85 unknown marker kind')
    if type(raw_results) is not list or len(raw_results) != len(pairs):
        raise GateError('C85 raw result count differs from complete marker pairs')
    for observed, result in zip(pairs, raw_results):
        if type(result) is not dict or result.get('id') != observed['request_id'] or \
           result.get('monotonic_request_markers_ns') != {
               'request_start':observed['request_start_ns'],
               'response_complete':observed['response_complete_ns']}:
            raise GateError('C85 raw and marker receipt disagree')
    if require_complete and (open_start is not None or len(pairs) != len(expected_ids)):
        raise GateError('C85 incomplete request marker receipt')
    return {'schema':'c85-marker-validation-v1',
            'status':'PASS' if open_start is None and len(pairs) == len(expected_ids) else 'INCOMPLETE_EVIDENCE',
            'complete_pairs':len(pairs), 'expected_pairs':len(expected_ids),
            'unmatched_start_request_id':open_start['request_id'] if open_start else None,
            'pairs':pairs}
