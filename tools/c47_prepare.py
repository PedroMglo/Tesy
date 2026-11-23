#!/usr/bin/env python3
"""Freeze C47 same-binary OFF/ON/fresh ON numeric boundary before outputs."""

import json
from pathlib import Path
import subprocess

from c2_gate import GateError, strict_json
from c8_observer_runner import model_stat
from run_bounded import backend_library_hashes, sha256
import c47_boundary_compare as compare
import c47_boundary_run as runner


ROOT = compare.ROOT
BACKEND = Path(runner.BACKEND)
SOURCE_COMMIT = '6a2c6c1'


def write_new(path, row):
    with Path(path).open('x') as stream:
        json.dump(row, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def command(*argv):
    return subprocess.check_output(argv, text=True, timeout=20).strip()


def main():
    protocol_path = ROOT/'protocol.json'
    test_path = ROOT/'model-free-tests.json'
    if protocol_path.exists() or test_path.exists():
        raise GateError('C47 preparation no-replace')
    commit = command('git','-C',str(BACKEND),'rev-parse','HEAD')
    if not commit.startswith(SOURCE_COMMIT) or command('git','-C',str(BACKEND),'status','--porcelain'):
        raise GateError('C47 source commit/cleanliness invalid')
    binary = Path(runner.BINARY)
    server = BACKEND/'build-c47-skip/bin/llama-server'
    if not binary.is_file() or not server.is_file():
        raise GateError('C47 binaries absent')
    libs = backend_library_hashes(str(binary), BACKEND)
    if not libs:
        raise GateError('C47 boundary mapped-library expectation absent')
    help_run = subprocess.run([str(server),'--help'],stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE,text=True,timeout=15)
    operator = subprocess.run(['/tmp/c47_operator_test'],capture_output=True,text=True,timeout=15)
    if help_run.returncode or operator.returncode or \
       operator.stdout.strip() != 'C47_OPERATOR_PASS F32 F16 parked/active/control':
        raise GateError('C47 model-free server/operator gate failed')
    c46 = strict_json(Path('results/c46-wave-phase-20260928T0857Z/decision.json').read_text())
    pre = strict_json(Path('results/c46-wave-phase-20260928T0857Z/preflight.json').read_text())
    if c46['status'] != 'COMPACTION_PROTOTYPE_INVESTMENT_SCREEN' or \
       pre['model']['sha256'] != '582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d' or \
       model_stat() != pre['model']['stat']:
        raise GateError('C47 C46 investment/model evidence invalid')
    prior = strict_json(Path('results/c7b-20260927T1206Z/protocol.json').read_text())
    proto = {
        'schema':'c47-skip-boundary-protocol-v1','status':'FROZEN_BEFORE_MODEL',
        'objective':'prove CPU parked-pair skip preserves selected full logits and 250 captured numeric states bitwise under one P12 pin',
        'hypothesis':'writing +0 for parked CPU MMID pairs and omitting their dot/activation conversion leaves active routed outputs bitwise unchanged',
        'alternative':'skipped inactive values influence downstream arithmetic, mapping/lifetime or graph behavior despite masking',
        'backend_commit':commit,
        'backend_tree':command('git','-C',str(BACKEND),'rev-parse','HEAD^{tree}'),
        'backend_source_sha256':{str(path):sha256(path) for path in
                                  (BACKEND/'src/llama-moe-stream.cpp',
                                   BACKEND/'ggml/src/ggml-cpu/ggml-cpu.c')},
        'capture_binary_sha256':sha256(binary),
        'server_binary_sha256':sha256(server),
        'backend_library_sha256':libs,
        'capture_source_sha256':sha256('tools/c47_boundary_capture.cpp'),
        'compare_sha256':sha256(compare.__file__),
        'runner_sha256':sha256(runner.__file__),
        'model_sha256':pre['model']['sha256'],'model_stat':model_stat(),
        'model_revision':'238abdd290bb874b90a5da1b4549881b7d05c091',
        'input_sha256':sha256(runner.IDS),
        'input_contract':prior['call_and_graph_plan'],
        'effective_options':prior['effective_options'],
        'run_order':list(compare.RUNS),
        'env_by_run':{
            compare.RUNS[0]:{'LLAMA_MOE_STREAM_NO_PRELOAD':'1'},
            compare.RUNS[1]:{'LLAMA_MOE_STREAM_NO_PRELOAD':'1','TESY_CPU_WAVE_SKIP_PARKED':'1'},
            compare.RUNS[2]:{'LLAMA_MOE_STREAM_NO_PRELOAD':'1','TESY_CPU_WAVE_SKIP_PARKED':'1'},
        },
        'same_profile_gate':'bitwise 5 complete 201088-F32 logits, all six core stages for 250 numeric states, fresh ON repeat; all finite; 2 masked N/A',
        'bytes_lifetime_gate':'active expert bytes/generation checked by C47 capture at witness layers 0,25,29,35',
        'canonical_reference':'same-pin C47 resident layer 36-load gate after this boundary, in a separately frozen unit; no timing promotion before it',
        'resource_envelope':'E18, zero cgroup swap, RSS<=16GiB, cgroup<=16.5GiB, GPU total<=6500MiB reservation, MemAvailable>=6GiB, CPU95 warning/100 stop, GPU80/NVMe70',
        'idle_admission':'300 contiguous seconds <=1s cadence; start <=55/55/50 CPU/GPU/NVMe and later arms within 5/5/3C of first baseline; max 900s',
        'timeout_per_arm_s':600,
        'failure_policy':'first mismatch/guard/OOM/telemetry/evidence failure stops unit; preserve raw and do not run later arms',
        'timing_promotable':False,'default_changed':False,
        'parent_c46_decision_sha256':sha256('results/c46-wave-phase-20260928T0857Z/decision.json'),
    }
    test = {
        'schema':'c47-model-free-tests-v1','status':'PASS',
        'initial_build_failure':'first source commit inserted conversion guard in generic MUL_MAT; preserved as b948e2d and corrected before model',
        'second_build_failure':'incomplete ggml_backend_buffer type dereference; corrected using public buffer API before model',
        'final_source_commit':commit,
        'build_flags':{'CMAKE_BUILD_TYPE':'Release','CMAKE_C_COMPILER':'/usr/bin/gcc-15',
                       'CMAKE_CXX_COMPILER':'/usr/bin/g++-15','CMAKE_CUDA_COMPILER':'/usr/local/cuda/bin/nvcc',
                       'CMAKE_CUDA_ARCHITECTURES':89,'GGML_CUDA':'ON',
                       'CMAKE_C_FLAGS':'TESY_C15_NVTX TESY_C47_CPU_SKIP_PARKED',
                       'CMAKE_CXX_FLAGS':'TESY_C15_NVTX TESY_C47_CPU_SKIP_PARKED'},
        'server_help_exit_code':help_run.returncode,
        'operator_result':operator.stdout.strip(),
        'operator_source_sha256':sha256('tools/c47_operator_test.cpp'),
        'operator_binary_sha256':sha256('/tmp/c47_operator_test'),
        'capture_binary_sha256':sha256(binary),
        'limit':'F32/F16 model-free operator cases do not qualify MXFP4 full-model or same-pin canonical reference',
    }
    write_new(protocol_path,proto)
    write_new(test_path,test)
    print(json.dumps({'status':'FROZEN_TOP','backend_commit':commit,
                      'capture_binary_sha256':proto['capture_binary_sha256']}))


if __name__ == '__main__':
    main()
