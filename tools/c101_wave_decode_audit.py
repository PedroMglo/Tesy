#!/usr/bin/env python3
"""Bounded source/build and C100 phase audit before a new wave toggle A/B."""

import json
from pathlib import Path
import subprocess

from c2_gate import GateError, strict_json
from run_bounded import sha256

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / 'results/c101-wave-decode-audit-20260928T2247Z'
C100 = REPO / 'results/c100-server-wave-confirm-20260928T2211Z'
BASE = Path('/tmp/tesy-c35-backend-20260928')
PATCHED = Path('/tmp/tesy-c75-backend-20260928')


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


def cache(path):
    value = {}
    for line in path.read_text().splitlines():
        if not line.startswith(('#', '//')) and ':' in line and '=' in line:
            key = line.split(':', 1)[0]
            value[key] = line.split('=', 1)[1]
    return value


def main():
    if ROOT.exists():
        raise GateError('C101 output root already exists')
    if git(BASE, 'rev-parse', 'HEAD') != 'c3759bad92c0e6f71bb936afea9b0a162fb83f76' or \
       git(PATCHED, 'rev-parse', 'HEAD') != '27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5' or \
       git(BASE, 'status', '--porcelain') or git(PATCHED, 'status', '--porcelain'):
        raise GateError('C101 backend identity/cleanliness changed')
    diff = git(PATCHED, 'diff', '--unified=0', git(BASE, 'rev-parse', 'HEAD'), 'HEAD', '--',
               'ggml/src/ggml-cpu/ggml-cpu.c', 'src/llama-moe-stream.cpp')
    if 'TESY_CPU_WAVE_SKIP_PARKED' not in diff or 'TESY_C47_CPU_SKIP_PARKED' not in diff:
        raise GateError('C101 expected source delta absent')
    a = cache(BASE/'build-c35-gcc15/CMakeCache.txt')
    b = cache(PATCHED/'build-c75-cuda/CMakeCache.txt')
    build_keys = sorted(k for k in set(a)|set(b) if k.startswith(('GGML_', 'LLAMA_')) or
                        k in ('CMAKE_C_FLAGS','CMAKE_CXX_FLAGS','CMAKE_BUILD_TYPE'))
    build_delta = {k:{'control':a.get(k),'candidate':b.get(k)} for k in build_keys
                   if a.get(k) != b.get(k)}
    expected = {'CMAKE_C_FLAGS','CMAKE_CXX_FLAGS','LLAMA_BUILD_TESTS'}
    if set(build_delta) != expected or \
       any('-DTESY_C47_CPU_SKIP_PARKED' not in b[k] for k in ('CMAKE_C_FLAGS','CMAKE_CXX_FLAGS')):
        raise GateError('C101 unexpected relevant CMake delta')
    manifest = strict_json((C100/'manifest.json').read_text())['raw']
    if any(sha256(C100/'raw'/name) != item['sha256'] for name,item in manifest.items()):
        raise GateError('C101 C100 raw manifest mismatch')
    decision = strict_json((C100/'decision.json').read_text())
    if decision['status'] != 'NO_GO_CONFIRM':
        raise GateError('C101 prior decision changed')
    timing = strict_json((C100/'timing-pairs.json').read_text())
    entries = []
    for pair in timing['pairs']:
        for arm in ('control','candidate'):
            run_id = pair[f'{arm}_run_id']
            raw = strict_json((C100/'raw'/f'{run_id}.json').read_text())
            samples = [strict_json(line) for line in
                       (C100/'raw'/f'{run_id}.samples.jsonl').read_text().splitlines()]
            for request in raw['results']:
                window = [x for x in samples
                          if request['started_s'] <= x['elapsed_s'] <= request['ended_s']]
                if not window:
                    raise GateError('C101 no thermal samples during request')
                entries.append({'run_id':run_id,'pair':pair['pair'],'arm':arm,
                                'request':request['id'],
                                'decode_s':request['timings']['predicted_ms']/1000,
                                'decode_tokens_per_s':request['timings']['predicted_per_second'],
                                'sampled_cpu_c_max':max(x['thermal']['cpu_tctl_c'] for x in window),
                                'sampled_gpu_c_max':max(x['gpu']['temperature_c'] for x in window),
                                'cpu_clock_samples':'NOT_CAPTURED_C100',
                                'wave_counts':'NOT_CAPTURED_C100'})
    ROOT.mkdir()
    result = {'schema':'c101-wave-decode-audit-v1','status':'SOURCE_AND_EXISTING_RAW_AUDITED',
              'evidence_class':['SOURCE_AUDITED','MEDIDO_NO_TARGET_C100_RAW_REUSE'],
              'source':{'control_commit':git(BASE,'rev-parse','HEAD'),
                        'candidate_commit':git(PATCHED,'rev-parse','HEAD'),
                        'control_tree':git(BASE,'rev-parse','HEAD^{tree}'),
                        'candidate_tree':git(PATCHED,'rev-parse','HEAD^{tree}'),
                        'diff_sha256':None, 'files_changed':2,
                        'mechanism':'host CPU wave IDs set to -1 for parked pairs when env enabled; CPU MMID writes zero for -1; shared activation conversion remains'},
              'build_relevant_delta':build_delta,
              'c100_decision_sha256':sha256(C100/'decision.json'),
              'c100_manifest_sha256':sha256(C100/'manifest.json'),
              'per_request':entries,
              'inference':'C100 cannot attribute decode regression to wave skip versus candidate build or uncontrolled runtime state; C100 did not capture CPU clocks or per-request wave counts.',
              'next_discriminant':'two new alternating C75 OFF/ON server pairs on the identical two-request input, same binary/libraries; freeze diagnostic rule and matched starts before model',
              'default_changed':False}
    import hashlib
    result['source']['diff_sha256'] = hashlib.sha256(diff.encode()).hexdigest()
    with (ROOT/'analysis.json').open('x') as out:
        json.dump(result,out,indent=2,sort_keys=True,allow_nan=False)
        out.write('\n')
    print(json.dumps({'status':result['status'],'requests':len(entries),
                      'build_delta':sorted(build_delta)},allow_nan=False))


if __name__ == '__main__':
    main()
