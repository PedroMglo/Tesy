#!/usr/bin/env python3
"""Record C54 model-free source, build and profiler checks before freezing."""

import json
from pathlib import Path
import sqlite3
import subprocess

from c2_gate import GateError
from run_bounded import backend_library_hashes, sha256
import c54_warm_phase as campaign


ROOT = campaign.ROOT
BACKEND = campaign.BACKEND
BINARY = campaign.BINARY
RAW = ROOT/'raw'


def call(*command):
    return subprocess.check_output(command, text=True, timeout=15).strip()


def main():
    out = ROOT/'model-free-tests.json'
    if out.exists():
        raise GateError('C54 model-free record no-replace')
    if campaign.git('-C', str(BACKEND), 'status', '--porcelain') or \
       campaign.git('-C', str(BACKEND), 'rev-list', '-3', 'HEAD').splitlines()[-1] != \
            'c3759bad92c0e6f71bb936afea9b0a162fb83f76':
        raise GateError('C54 backend does not have clean C35+2 source ancestry')
    allowed = {'ggml/src/ggml-cpu/ggml-cpu.c', 'src/llama-moe-stream.cpp',
               'tools/server/server-context.cpp'}
    changed = set(campaign.git('-C',str(BACKEND),'diff','--name-only',
                               'c3759bad92c0e6f71bb936afea9b0a162fb83f76..HEAD').splitlines())
    if changed != allowed:
        raise GateError('C54 diagnostic source file delta unexpected')
    cache = (BACKEND/'build-c54-nvtx/CMakeCache.txt').read_text()
    if not all(s in cache for s in ('CMAKE_CUDA_ARCHITECTURES:UNINITIALIZED=89',
                                    'CMAKE_CXX_FLAGS:STRING=-DTESY_C15_NVTX',
                                    'CMAKE_C_FLAGS:STRING=-DTESY_C15_NVTX',
                                    'GGML_CUDA:BOOL=ON')):
        raise GateError('C54 build flags differ')
    target = BACKEND/'build-c54-nvtx/bin'
    symbols = {
        'libggml-cpu.so':(b'C15_CPU_STREAM_MATMUL_ID',),
        'libllama.so':(b'C15_EXPERT_PREAD',b'C15_EXPERT_UPLOAD',b'C46_WAVE_LAYER='),
        'libllama-server-impl.so':(b'C46_SERVER_PREFILL_DECODE',
                                   b'C46_SERVER_GENERATION_DECODE'),
    }
    for library, labels in symbols.items():
        data = (target/library).read_bytes()
        if any(label not in data for label in labels):
            raise GateError(f'C54 diagnostic label absent from {library}')
    help_run = subprocess.run([str(BINARY),'--help'],stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE,text=True,timeout=15)
    if help_run.returncode:
        raise GateError('C54 server model-free --help failed')
    db = RAW/'c54-nvtx-smoke.sqlite'
    report = RAW/'c54-nvtx-smoke.nsys-rep'
    with sqlite3.connect(db) as conn:
        events = conn.execute("select eventType,text,end from NVTX_EVENTS "
                              "where text like 'C46_%' order by start").fetchall()
    if len(events) != 2 or events[0][0:2] != (59,'C46_SERVER_PREFILL_DECODE') or \
       events[0][2] is None or \
       events[1] != (34,'C46_WAVE_LAYER=0_WAVE=0_ACTIVE=1_OF=32',None):
        raise GateError('C54 model-free NVTX profiler smoke failed')
    record = {
        'schema':'c54-model-free-tests-v1','status':'PASS',
        'source_commit':campaign.git('-C',str(BACKEND),'rev-parse','HEAD'),
        'source_tree':campaign.git('-C',str(BACKEND),'rev-parse','HEAD^{tree}'),
        'source_clean':True,'changed_files':sorted(changed),
        'build_cache_sha256':sha256(BACKEND/'build-c54-nvtx/CMakeCache.txt'),
        'binary_sha256':sha256(BINARY),
        'library_sha256':backend_library_hashes(str(BINARY),BACKEND),
        'help_exit_code':help_run.returncode,
        'smoke_events':[{'event_type':kind,'text':label} for kind,label,_ in events],
        'smoke_source_sha256':sha256('tools/c54_nvtx_smoke.cpp'),
        'smoke_report_sha256':sha256(report),
        'smoke_sqlite_sha256':sha256(db),
        'analyzer_controls':'PASS',
        'limits':['source/build/profiler checked without model; actual phase coverage unknown',
                  'instrumented run is diagnostic; no production timing promotion'],
    }
    if not record['library_sha256']:
        raise GateError('C54 backend library hashes absent')
    with out.open('x') as stream:
        json.dump(record,stream,indent=2,sort_keys=True,allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status':'PASS','source_commit':record['source_commit']}))


if __name__ == '__main__':
    main()
