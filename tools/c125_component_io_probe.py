#!/usr/bin/env python3
"""Bounded, read-only O_DIRECT screen of C123 exact expert component offsets.

One arm reads three components serially per expert with four workers. The
other reads components independently with twelve workers. Groups retain the
observed (call, layer) order, with a barrier between groups. This is a storage
mechanism probe, not a reproduction of server compute or a speedup forecast.
"""

import argparse
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import mmap
import os
from pathlib import Path
import statistics
import subprocess
import threading
import time

from c2_gate import GateError, strict_json
from c118_start_inventory import live_sample, validate_sample
from c123_analyze_trace import EXPECTED_TRACE_SHA, trace_rows, sha
from c122_trace_validate import validate
from c9_server_admission import MODEL, MODEL_SHA
from host_resource_policy import GIB
from run_bounded import relevant_environment
import c2_server_run as server

REPO = Path(__file__).resolve().parents[1]
TRACE = REPO / 'results/c123-warm153-decode-trace-20260929T1450Z/raw/c123-c75-warm153.expert.trace'
INVENTORY = REPO / 'results/c7-20260927T1130Z/raw/gguf-inventory.jsonl'
INVENTORY_SHA = '2c8ca725f50000bf3177712cfa30d29a809f77f25826b425ea67d8fcbffd6d82'
POLICY = REPO / 'results/c124-nominal153-confirm-20260929T1515Z/resource-policy.json'
CAP = 18 * GIB
ORDER = ('serial', 'parallel', 'parallel', 'serial')
ALIGN = 4096
MAX_ARM_S = 180
LOCAL = threading.local()


def git(*args):
    return subprocess.check_output(['git', *args], text=True, cwd=REPO).strip()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def inventory_offsets():
    if sha(INVENTORY) != INVENTORY_SHA:
        raise GateError('C125 GGUF metadata identity changed')
    rows = [json.loads(line) for line in INVENTORY.read_text().splitlines()]
    offsets = {}
    for row in rows[1:]:
        name = row.get('name', '')
        bits = name.split('.')
        if len(bits) != 4 or bits[0] != 'blk' or not bits[1].isdigit() or bits[3] != 'weight' or \
           bits[2] not in ('ffn_down_exps', 'ffn_gate_exps', 'ffn_up_exps'):
            continue
        layer = int(bits[1]); component = bits[2]
        if row.get('tensor_type') != 'mxfp4' or row.get('shape') != [2880, 2880, 128] or \
           row['n_bytes'] % 128:
            raise GateError('C125 expert tensor metadata incompatible')
        offsets[(layer, component)] = (row['data_offset'], row['n_bytes']//128)
    if len(offsets) != 36*3:
        raise GateError('C125 incomplete expert tensor metadata')
    return offsets


def groups():
    if sha(TRACE) != EXPECTED_TRACE_SHA:
        raise GateError('C125 C123 trace identity changed')
    validate(TRACE)
    layers, events = trace_rows(TRACE)
    offsets = inventory_offsets()
    grouped = OrderedDict()
    total = 0
    for e in events:
        if e['kind'] != 'LOAD_BEGIN' or e['call_id'] < 3:
            continue
        layer, expert = e['layer'], e['expert']
        if not 0 <= layer < 36 or not 0 <= expert < 128:
            raise GateError('C125 expert identity invalid')
        components = []
        for name in ('ffn_down_exps', 'ffn_gate_exps', 'ffn_up_exps'):
            base, size = offsets[(layer, name)]
            components.append((base + expert*size, size))
            total += size
        grouped.setdefault((e['call_id'], layer), []).append(components)
    if sum(len(v) for v in grouped.values()) != 1509 or total != 19947772800:
        raise GateError('C125 decode load count/bytes changed')
    return list(grouped.values()), total


def read_component(fd, item):
    offset, length = item
    aligned_offset = offset & ~(ALIGN-1)
    head = offset-aligned_offset
    total = ((head+length+ALIGN-1)//ALIGN)*ALIGN
    if total > getattr(LOCAL, 'buffer_size', 0):
        old = getattr(LOCAL, 'buffer', None)
        if old is not None: old.close()
        LOCAL.buffer = mmap.mmap(-1, total)
        LOCAL.buffer_size = total
    view = memoryview(LOCAL.buffer)[:total]
    try:
        count = os.preadv(fd, [view], aligned_offset)
    finally:
        view.release()
    if count < head + length:
        raise GateError('C125 short direct read')
    return length


def serial_expert(fd, components):
    return sum(read_component(fd, item) for item in components)


def measure_arm(mode, workload, policy):
    if mode not in ('serial', 'parallel'):
        raise GateError('C125 mode invalid')
    expected_power = {k:policy['power'][k] for k in ('source','profile')}
    before = live_sample()
    validate_sample(before, policy=policy, cap_bytes=0, expected_power=expected_power)
    flags = os.O_RDONLY | getattr(os, 'O_DIRECT', 0)
    if not hasattr(os, 'O_DIRECT'):
        raise GateError('C125 O_DIRECT unsupported')
    fd = os.open(MODEL, flags)
    stop = threading.Event()
    monitor_errors = []
    observations = []
    def monitor():
        while not stop.wait(2):
            try:
                sample = live_sample()
                validate_sample(sample, policy=policy, cap_bytes=0,
                                expected_power=expected_power)
                observations.append(sample)
            except Exception as exc:
                monitor_errors.append(f'{type(exc).__name__}: {exc}')
                stop.set()
    ticker = threading.Thread(target=monitor, daemon=True)
    started = datetime.now(timezone.utc)
    begin = time.monotonic()
    bytes_read = 0
    group_durations = []
    try:
        ticker.start()
        with ThreadPoolExecutor(max_workers=4 if mode=='serial' else 12) as pool:
            for group in workload:
                if stop.is_set() or time.monotonic()-begin > MAX_ARM_S:
                    raise GateError('C125 resource stop or arm timeout')
                t = time.monotonic()
                if mode == 'serial':
                    futures = [pool.submit(serial_expert, fd, components) for components in group]
                else:
                    futures = [pool.submit(read_component, fd, item)
                               for components in group for item in components]
                bytes_read += sum(f.result() for f in futures)
                group_durations.append(time.monotonic()-t)
        after = live_sample()
        validate_sample(after, policy=policy, cap_bytes=0, expected_power=expected_power)
        if monitor_errors:
            raise GateError('C125 monitor: '+monitor_errors[0])
        return {'status':'PASS_MODEL_FREE_IO','mode':mode,'started_utc':started.isoformat(),
                'ended_utc':datetime.now(timezone.utc).isoformat(),
                'elapsed_s':time.monotonic()-begin,'logical_bytes':bytes_read,
                'groups':len(workload),'group_duration_s':group_durations,
                'start_observation':before,'end_observation':after,
                'monitor_sample_count':len(observations),'monitor_errors':monitor_errors}
    finally:
        stop.set()
        if ticker.is_alive(): ticker.join(timeout=3)
        os.close(fd)


def freeze(root):
    if not root.is_dir() or not (root/'raw').is_dir() or (root/'protocol.json').exists():
        raise GateError('C125 new root required')
    workload,total=groups()
    policy=strict_json(POLICY.read_text())
    state=server.cgroup_state()
    if not state or state['memory_max'] != CAP or state['swap_max'] != 0:
        # Freeze is model-free; caller may invoke in a small real E18 scope.
        raise GateError('C125 E18/zero-swap scope required')
    stat=Path(MODEL).stat()
    if stat.st_size != 63387346208 or policy['memory']['cap_max_bytes'] < CAP:
        raise GateError('C125 model stat or capacity changed')
    protocol={'schema':'c125-component-io-v1','campaign_id':root.name,
              'status':'FROZEN_NOT_MEASURED',
              'source_commit':git('rev-parse','HEAD'),'order':list(ORDER),
              'trace_sha256':sha(TRACE),'gguf_inventory_sha256':sha(INVENTORY),
              'resource_policy_sha256':sha(POLICY),'model_path':str(MODEL),
              'model_sha256_from_prior_verified_provenance':MODEL_SHA,
              'model_stat':{'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'inode':stat.st_ino},
              'group_digest':digest(workload),'group_count':len(workload),
              'load_count':1509,'logical_bytes_per_arm':total,
              'modes':{'serial':'4 workers, 3 component reads serial per expert',
                       'parallel':'12 workers, 3 component reads concurrent per expert'},
              'direct_io':True,'barrier':'after each observed call/layer group',
              'arm_timeout_s':MAX_ARM_S,'raw_limit_bytes':2**20,
              'decision':'two paired ABBA read-only elapsed gains; both positive and median >=15% warrants one bounded backend prototype; otherwise NO_GO',
              'claim_limit':'storage-only fixed observed miss sequence; not server decode time'}
    (root/'protocol.json').write_text(json.dumps(protocol,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':'FROZEN_NOT_MEASURED','groups':len(workload),'loads':1509,'bytes_per_arm':total}))


def run(root, commit):
    if git('rev-parse','HEAD') != commit or git('status','--porcelain') or relevant_environment(os.environ):
        raise GateError('C125 measurement commit/worktree/environment changed')
    protocol=strict_json((root/'protocol.json').read_text())
    workload,total=groups()
    if protocol.get('campaign_id') != root.name or protocol['group_digest'] != digest(workload) or protocol['logical_bytes_per_arm'] != total or \
       protocol['trace_sha256'] != sha(TRACE) or protocol['resource_policy_sha256'] != sha(POLICY):
        raise GateError('C125 frozen source/workload/policy changed')
    stat=Path(MODEL).stat()
    if {'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'inode':stat.st_ino} != protocol['model_stat']:
        raise GateError('C125 model stat changed')
    state=server.cgroup_state()
    if not state or state['memory_max'] != CAP or state['swap_max'] != 0:
        raise GateError('C125 scope changed')
    policy=strict_json(POLICY.read_text())
    rows=[]
    for i,mode in enumerate(ORDER,1):
        path=root/'raw'/f'arm{i}-{mode}.json'
        if path.exists(): raise GateError('C125 arm output identity already exists')
        try:
            row=measure_arm(mode,workload,policy)
        except Exception as exc:
            row={'status':'FAIL_MODEL_FREE_IO','mode':mode,'error':f'{type(exc).__name__}: {exc}',
                 'utc':datetime.now(timezone.utc).isoformat()}
        row.update({'arm_index':i,'measurement_commit':commit,'protocol_sha256':sha(root/'protocol.json')})
        path.write_text(json.dumps(row,indent=2,sort_keys=True,allow_nan=False)+'\n')
        rows.append(row)
        print(json.dumps({'arm':i,'mode':mode,'status':row['status'],'elapsed_s':row.get('elapsed_s')}),flush=True)
        if row['status']!='PASS_MODEL_FREE_IO':break
    return 0 if len(rows)==4 and all(r['status']=='PASS_MODEL_FREE_IO' for r in rows) else 1


def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('freeze','run'))
    ap.add_argument('root',type=Path);ap.add_argument('--measurement-commit');args=ap.parse_args()
    root=args.root.resolve()
    if args.mode=='freeze':freeze(root)
    else:
        if not args.measurement_commit:ap.error('run needs measurement commit')
        raise SystemExit(run(root,args.measurement_commit))


if __name__=='__main__':main()
