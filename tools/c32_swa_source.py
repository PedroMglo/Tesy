#!/usr/bin/env python3
"""Model-free check of actual C29/C31 server SWA and checkpoint settings."""

import datetime as dt
import json
from pathlib import Path

from c2_gate import GateError, strict_json
from run_bounded import sha256


ROOT = Path('results/c32-swa-source-20260928T0026Z')
BACKEND = Path('/home/pmglo/Projects/Tesy/tesy-scale-lab/backends/streaming')
INPUTS = {
    'C29_preflight_sha256': Path('results/c29-conversation-bridge-20260927T2252Z/raw/c29-g1-prefix2048.preflight.json'),
    'C31_preflight_sha256': Path('results/c31-cache-reproduction-20260927T2342Z/raw/c31-d3-prefix2048.preflight.json'),
    'server_context_source_sha256': BACKEND/'tools/server/server-context.cpp',
    'kv_iswa_source_sha256': BACKEND/'src/llama-kv-cache-iswa.cpp',
    'C31_decision_sha256': Path('results/c31-cache-reproduction-20260927T2342Z/decision.json'),
}


def save_new(path, row):
    with path.open('x') as out:
        json.dump(row, out, sort_keys=True, indent=2, allow_nan=False)
        out.write('\n')


def main():
    protocol = strict_json((ROOT/'protocol.json').read_text())
    if protocol['schema'] != 'c32-swa-source-protocol-v1':
        raise GateError('C32 protocol changed')
    for field, path in INPUTS.items():
        if sha256(path) != protocol[field]:
            raise GateError(f'C32 frozen input changed: {field}')
    configs = {}
    for label in ('C29', 'C31'):
        preflight = strict_json(INPUTS[f'{label}_preflight_sha256'].read_text())
        command = preflight['config']['server_command']
        if command.count('--swa-full') != 1 or command.count('--cache-ram') != 1 or \
                command[command.index('--cache-ram')+1] != '0' or \
                command.count('--ctx-checkpoints') != 1 or \
                command[command.index('--ctx-checkpoints')+1] != '0':
            raise GateError(f'{label} effective command differs from C32 hypothesis')
        configs[label] = {'swa_full': True, 'cache_ram_mib': 0,
                          'ctx_checkpoints': 0,
                          'server_binary': command[0],
                          'protocol_sha256': preflight['protocol_sha256']}
    source = INPUTS['server_context_source_sha256'].read_text()
    kv_source = INPUTS['kv_iswa_source_sha256'].read_text()
    required = ('n_swa = params_base.swa_full ? 0 : llama_model_n_swa(model_tgt);',
                'do_checkpoint = do_checkpoint && (',
                'n_swa > 0);')
    if any(marker not in source for marker in required) or \
            'if (swa_full) {' not in kv_source or \
            'size_swa = size_base;' not in kv_source:
        raise GateError('C32 source semantics changed')
    c29_log = Path('results/c29-conversation-bridge-20260927T2252Z/raw/c29-g1-prefix2048.stderr').read_text()
    c31_log = Path('results/c31-cache-reproduction-20260927T2342Z/raw/c31-d3-prefix2048.stderr').read_text()
    for label, log in (('C29', c29_log), ('C31', c31_log)):
        if 'using full-size SWA cache' not in log or \
                'creating     SWA KV cache, size = 8192 cells' not in log or \
                'context checkpoints disabled' not in log:
            raise GateError(f'{label} loaded-state SWA evidence incomplete')
    audit = {'schema': 'c32-swa-source-audit-v1', 'evidence_class': 'MODEL_FREE_SOURCE_AND_EXISTING_RAW',
             'configs': configs,
             'loaded_state': {'C29': 'full-size SWA KV 8192 cells; checkpoints disabled',
                              'C31': 'full-size SWA KV 8192 cells; checkpoints disabled'},
             'source_semantics': 'swa_full sets server n_swa=0 and SWA KV size equal to base; checkpoint creation disabled by command',
             'capacity_delta_for_turning_on_swa_full': 0,
             'claim_limit': 'C29 verbosity-3 log cannot distinguish server-held token mismatch from a rare reset; absence of checkpoint markers there is not proof',
             'model_runs': 0}
    save_new(ROOT/'audit.json', audit)
    decision = {'schema': 'c32-swa-source-decision-v1',
                'status': 'SWA_FULL_ALREADY_ACTIVE_NO_NEW_PROFILE',
                'C31_suggested_next_action': 'REFUTED_BY_EFFECTIVE_COMMAND_AND_LOADED_STATE',
                'C29_failure_preserved': 'cache_n35 FAIL_RESOURCES_OR_EVIDENCE',
                'C31_diagnostic_preserved': 'three cache_n2036 hits; miss cause unknown',
                'next_action': 'C15 source-only wave interval probe: validate instrumented boundary and build/model-free gates before bounded full-model critical-path diagnostic; do not promote instrumented times',
                'm3': 'PARTIAL_TRUE_CONVERSATION_CACHE_UNRELIABLE', 'm4': 'NOT_RUN',
                'c15': 'SOURCE_ONLY_NOT_COMPILED_NOT_MEASURED',
                'default_changed': False}
    save_new(ROOT/'decision.json', decision)
    save_new(ROOT/'manifest.json', {'schema': 'c32-closure-manifest-v1',
                                   'protocol_sha256': sha256(ROOT/'protocol.json'),
                                   'inputs_sha256': {field: sha256(path) for field,path in INPUTS.items()},
                                   'audit_sha256': sha256(ROOT/'audit.json'),
                                   'decision_sha256': sha256(ROOT/'decision.json'),
                                   'closed_utc': dt.datetime.now(dt.timezone.utc).isoformat()})
    with (ROOT/'LEDGER.md').open('a') as out:
        out.write('\n- Source and effective C29/C31 commands confirm `--swa-full`, `--cache-ram 0`, `--ctx-checkpoints 0`; both logs report 8192-cell full SWA KV. C32 closes without a model run. C31 suggested full-SWA switch is redundant. C29 FAIL remains; C15 source/build feasibility is next.\n')
    print(json.dumps({'status': decision['status'], 'model_runs': 0}))


if __name__ == '__main__':
    main()
