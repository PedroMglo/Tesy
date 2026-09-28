#!/usr/bin/env python3
"""Recheck the isolated C75 session port without loading a model."""
import json
from pathlib import Path
import subprocess
import sys

from run_bounded import sha256

REPO = Path(__file__).resolve().parents[1]
BACKEND = Path('/tmp/tesy-c75-backend-20260928')
SOURCE = '27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5'
BASE = 'c3759bad92c0e6f71bb936afea9b0a162fb83f76'
BIN = BACKEND / 'build-c75-cuda/bin'
OUTPUT = REPO / 'results/c75-session-wave-port-20260928T1907Z/model-free-tests.json'


def command(args):
    p = subprocess.run(args, text=True, capture_output=True, check=False)
    return {'argv': [str(x) for x in args], 'returncode': p.returncode,
            'stdout': p.stdout, 'stderr': p.stderr}


def main():
    if OUTPUT.exists():
        raise RuntimeError('C75 no-replace output exists')
    head = subprocess.check_output(['git', '-C', str(BACKEND), 'rev-parse', 'HEAD'], text=True).strip()
    parent = subprocess.check_output(['git', '-C', str(BACKEND), 'rev-parse', 'HEAD^'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(BACKEND), 'status', '--porcelain'], text=True)
    if (head, parent, dirty) != (SOURCE, BASE, ''):
        raise RuntimeError('C75 source/base/dirty state changed')
    include = BACKEND / 'ggml/include'
    products = {}
    checks = {}
    for name, file in [('broadcast', 'c57_broadcast_operator.cpp'),
                       ('ffn', 'c57_ffn_operator_test.cpp')]:
        binary = Path('/tmp') / ('c75_' + name + '_operator')
        build = command(['g++-15', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                         '-I', include, REPO / 'tools' / file,
                         '-L', BIN, '-Wl,-rpath,' + str(BIN),
                         '-lggml-cpu', '-lggml-base', '-lggml', '-o', binary])
        if build['returncode']:
            raise RuntimeError(f'{name} build failed: {build["stderr"]}')
        result = command([binary, '--expect-fixed'])
        checks[name] = result
        products[str(binary)] = sha256(binary)
    for file in ('llama-server', 'libggml-base.so.0.15.3',
                 'libggml-cpu.so.0.15.3', 'libggml-cuda.so.0.15.3',
                 'libllama.so.0.0.3'):
        products[str(BIN / file)] = sha256(BIN / file)
    status = 'PASS_MODEL_FREE' if all(x['returncode'] == 0 for x in checks.values()) else 'FAIL_MODEL_FREE'
    record = {'schema': 'c75-model-free-v1', 'status': status,
              'source_commit': head, 'source_tree': subprocess.check_output(
                  ['git', '-C', str(BACKEND), 'rev-parse', 'HEAD^{tree}'], text=True).strip(),
              'source_base': parent, 'backend_path': str(BACKEND),
              'patch_sha256': sha256(REPO / 'research/patches/C75-session-wave-skip-port.patch'),
              'test_source_sha256': {name: sha256(REPO / 'tools' / file)
                  for name, file in [('broadcast', 'c57_broadcast_operator.cpp'),
                                     ('ffn', 'c57_ffn_operator_test.cpp')]},
              'build_products_sha256': products, 'checks': checks,
              'claim': 'MXFP4/F16/F32 synthetic broadcast and FFN only; no 120B or session fidelity claim'}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open('x') as stream:
        json.dump(record, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': status, 'output': str(OUTPUT)}))
    return 0 if status == 'PASS_MODEL_FREE' else 1


if __name__ == '__main__':
    sys.exit(main())
