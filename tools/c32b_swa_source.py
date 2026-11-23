#!/usr/bin/env python3
"""Audit the existing full-SWA server profile with each log's actual level."""

import datetime as dt
import json
from pathlib import Path

from c2_gate import GateError, strict_json
from run_bounded import sha256
from c32_swa_source import INPUTS


ROOT = Path('results/c32b-swa-source-20260928T0028Z')
C29_LOG = Path('results/c29-conversation-bridge-20260927T2252Z/raw/c29-g1-prefix2048.stderr')
C31_LOG = Path('results/c31-cache-reproduction-20260927T2342Z/raw/c31-d3-prefix2048.stderr')
C32_FAIL = Path('results/c32-swa-source-20260928T0026Z/decision.json')


def save_new(path, row):
    with path.open('x') as out:
        json.dump(row, out, sort_keys=True, indent=2, allow_nan=False)
        out.write('\n')


def main():
    protocol = strict_json((ROOT/'protocol.json').read_text())
    if protocol['schema'] != 'c32b-swa-source-protocol-v1':
        raise GateError('C32b protocol changed')
    paths = dict(INPUTS)
    paths.update(C29_stderr_sha256=C29_LOG, C31_stderr_sha256=C31_LOG,
                 C32_failure_decision_sha256=C32_FAIL)
    for name,path in paths.items():
        if sha256(path) != protocol[name]:
            raise GateError(f'C32b input changed: {name}')
    if strict_json(C32_FAIL.read_text())['status'] != 'FAIL_HARNESS_EVIDENCE_ASSUMPTION':
        raise GateError('C32 failure was altered')
    effective = {}
    for label in ('C29','C31'):
        cfg = strict_json(INPUTS[f'{label}_preflight_sha256'].read_text())['config']
        args = cfg['server_command']
        if args.count('--swa-full') != 1 or args.count('--cache-ram') != 1 or \
                args[args.index('--cache-ram')+1] != '0' or \
                args.count('--ctx-checkpoints') != 1 or \
                args[args.index('--ctx-checkpoints')+1] != '0':
            raise GateError(f'{label} effective command differs')
        effective[label] = {'swa_full': True, 'cache_ram_mib': 0,
                            'ctx_checkpoints': 0, 'binary': args[0]}
    source = INPUTS['server_context_source_sha256'].read_text()
    kv_source = INPUTS['kv_iswa_source_sha256'].read_text()
    if 'n_swa = params_base.swa_full ? 0 : llama_model_n_swa(model_tgt);' not in source or \
            'do_checkpoint = do_checkpoint && (' not in source or \
            'size_swa = size_base;' not in kv_source:
        raise GateError('source relation changed')
    c29_log, c31_log = C29_LOG.read_text(), C31_LOG.read_text()
    if 'using full-size SWA cache' not in c29_log or \
            'using full-size SWA cache' not in c31_log or \
            'creating     SWA KV cache, size = 8192 cells' not in c31_log or \
            'context checkpoints disabled' not in c31_log:
        raise GateError('C32b level-aware loaded-state evidence missing')
    audit = {'schema': 'c32b-swa-source-audit-v1',
             'evidence_class': 'MODEL_FREE_SOURCE_AND_EXISTING_RAW',
             'effective_config': effective,
             'C29_loaded_warning': 'using full-size SWA cache',
             'C29_info_lines': 'UNAVAILABLE_AT_VERBOSITY_3',
             'C31_loaded_info': '8192 SWA KV cells; context checkpoints disabled',
             'source_semantics': 'swa_full selects SWA cache size equal to base and server n_swa=0',
             'new_capacity_delta_from_enabling_swa_full': 0,
             'C29_low_cache_cause': 'UNKNOWN_WITHOUT_TOKEN_WINDOW_TRACE',
             'model_runs': 0}
    save_new(ROOT/'audit.json',audit)
    decision = {'schema': 'c32b-swa-source-decision-v1',
                'status': 'SWA_FULL_ALREADY_ACTIVE_NO_NEW_PROFILE',
                'C32_failure_preserved': True,
                'C31_suggested_full_swa_next_action': 'REFUTED_AS_REDUNDANT',
                'C29_failure_preserved': 'cache_n35 FAIL_RESOURCES_OR_EVIDENCE',
                'next_action': 'C15 source/build/model-free viability, then bounded wave critical-path diagnostic only if instrumentation can identify exclusive removable time; preserve timing as diagnostic',
                'c15': 'SOURCE_ONLY_NOT_COMPILED_NOT_MEASURED',
                'm3': 'PARTIAL_TRUE_CONVERSATION_CACHE_UNRELIABLE', 'm4': 'NOT_RUN',
                'default_changed': False}
    save_new(ROOT/'decision.json',decision)
    save_new(ROOT/'manifest.json',{'schema':'c32b-closure-manifest-v1',
                                   'protocol_sha256':sha256(ROOT/'protocol.json'),
                                   'inputs_sha256':{name:sha256(path) for name,path in paths.items()},
                                   'audit_sha256':sha256(ROOT/'audit.json'),
                                   'decision_sha256':sha256(ROOT/'decision.json'),
                                   'closed_utc':dt.datetime.now(dt.timezone.utc).isoformat()})
    with (ROOT/'LEDGER.md').open('a') as out:
        out.write('\n- C29/C31 commands both have `--swa-full`, `--cache-ram 0`, `--ctx-checkpoints 0`; C29 WARN and C31 INFO confirm full-size SWA loaded. No new SWA-full profile or model run. C29 cache_n35 remains unexplained; C15 source/build viability is next.\n')
    print(json.dumps({'status':decision['status'],'model_runs':0}))


if __name__ == '__main__':
    main()
