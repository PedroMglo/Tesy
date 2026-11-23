#!/usr/bin/env python3
"""Tensor-derived P14/P16 placement bound; no model execution."""
import argparse
import json
from pathlib import Path

from c2_gate import GateError,strict_json
from c7_accounting import account,digest

ROOT=Path(__file__).resolve().parents[1]
INVENTORY=ROOT/'results/c7-20260927T1130Z/raw/gguf-inventory.jsonl'
OLD_ACCOUNT=ROOT/'results/c7-20260927T1130Z/accounting.json'
C52B=ROOT/'results/c52b-assistant-history-sustained-20260928T1132Z/decision.json'
C58=ROOT/'results/c58-policy-canary-20260928T1443Z/decision.json'
C58_POLICY=ROOT/'results/c58-policy-canary-20260928T1443Z/resource-policy.json'
MIB=2**20

def calculate():
    old=strict_json(OLD_ACCOUNT.read_text())
    if digest(INVENTORY)!=old['inventory_sha256']:
        raise GateError('C7 tensor inventory SHA changed')
    measured=account(INVENTORY)
    if measured!=old:raise GateError('C7 tensor accounting changed')
    pool=old['slot_pool_per_layer_bytes']
    dense=old['profiles']['P12']['gpu_nonstream_layer_gguf_bytes']//11
    if pool!=423014400 or dense!=34155008:
        raise GateError('streamed pool/dense layer bytes changed')
    c52=strict_json(C52B.read_text());c58=strict_json(C58.read_text())
    if c52['completed_requests']!=20 or c58['status']!='PASS_POLICY_CANARY_TESTED_SCOPE':
        raise GateError('measured P12 controls unavailable')
    control_peak=max(c52['maxima']['gpu_total_mib'],c58['maxima']['gpu_total_mib'])
    policy=strict_json(C58_POLICY.read_text())
    gpu_stop=policy['gpu']['memory_stop_total_mib']
    results={}
    for name,ngl in (('P12',12),('P14',14),('P16',16)):
        gpu_layers=ngl-1
        cpu_layers=36-gpu_layers
        moved=ngl-12
        delta=moved*(pool+dense)
        estimated=control_peak+delta/MIB
        results[name]={
            'ngl':ngl,'slots':32,'cpu_layers':cpu_layers,
            'gpu_layers':gpu_layers,'cpu_layer_range':[0,cpu_layers-1],
            'gpu_layer_range':[cpu_layers,35],
            'cpu_expert_pools_bytes':cpu_layers*pool,
            'gpu_expert_pools_bytes':gpu_layers*pool,
            'gpu_nonstream_layer_gguf_bytes':gpu_layers*dense,
            'delta_gpu_pool_and_dense_bytes_from_P12':delta,
            'observed_P12_peak_plus_known_delta_mib_before_new_workspace':estimated,
            'remaining_mib_before_new_workspace':gpu_stop-estimated,
            'static_admission':('CONTROL' if moved==0 else
                'BOUNDED_FORWARD_REQUIRED' if estimated<gpu_stop else 'NOT_ADMITTED')}
    return {'schema':'c59-placement-accounting-v1','evidence_class':'TENSOR_ACCOUNTING_PLUS_MEASURED_P12_PEAK',
            'inventory_sha256':old['inventory_sha256'],
            'control_peak_mib':control_peak,'gpu_total_stop_mib':gpu_stop,
            'pool_per_layer_bytes':pool,'dense_per_layer_bytes':dense,
            'profiles':results,
            'unknown':['new CUDA graph/workspace/allocator reserve','routing and arithmetic under P14/P16',
                       'latency and thermal behavior','CPU/GPU cgroup charge shifts'],
            'decision':'P14 may proceed to bounded init and short forward after own numeric profile freeze; P16 is not admitted by this static bound alone',
            'model_loaded':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    with args.output.open('x') as out:
        json.dump(calculate(),out,indent=2,sort_keys=True,allow_nan=False);out.write('\n')
