"""Strict native upstream boundary coverage; never cross-profile bitwise claims."""
import csv
import hashlib
import math
from pathlib import Path
import struct

PHASES=('prefill0','prefill128','prefill_final','decode0','decode1','decode7','decode31')
STAGES=('attn_post_norm','ffn_moe_logits','ffn_moe_logits_biased','ffn_moe_topk','ffn_moe_weights_softmax','ffn_moe_out')

def payload(row,data):
    shape=tuple(map(int,row['ne'].split(',')));stride=tuple(map(int,row['nb'].split(',')))
    n=32 if row['phase'] in ('prefill0','prefill128') else 29 if row['phase']=='prefill_final' else 1
    stage=row['name'];expected=(4,n,1,1) if stage=='ffn_moe_topk' else (1,4,n,1) if stage=='ffn_moe_weights_softmax' else (128,n,1,1) if 'logits' in stage else (2880,n,1,1)
    if shape!=expected or len(stride)!=4 or len(data)!=int(row['bytes']) or not data or any(x<=0 for x in stride):raise ValueError('state shape/bytes/strides')
    if sum((a-1)*b for a,b in zip(shape,stride))+4>len(data):raise ValueError('state truncated')
    if stage=='ffn_moe_topk':
        if row['type']!='i32':raise ValueError('route dtype')
        for j in range(n):
            ids=[struct.unpack_from('<i',data,j*stride[1]+k*stride[0])[0] for k in range(4)]
            if len(set(ids))!=4 or any(not 0<=x<128 for x in ids):raise ValueError('route IDs')
    else:
        if row['type']!='f32' or len(data)%4:raise ValueError('float payload')
        if any(not math.isfinite(v[0]) for v in struct.iter_unpack('<f',data)):raise ValueError('nonfinite state')

def byte_entry(row,tensors):
    layer=int(row['layer']);kind=int(row['component']);expert=int(row['expert'])
    if not 0<=layer<36 or not 0<=kind<6 or not 0<=expert<128 or row['status']!='PASS' or row['buffer']!='CPU_Mapped':raise ValueError('byte check identity')
    name=f'blk.{layer}.ffn_{("gate","up","down")[kind%3]}_exps.{"weight" if kind<3 else "bias"}'
    t=tensors[name];per=t['n_bytes']//128
    if int(row['bytes'])!=per or int(row['offset'])!=t['data_offset']+expert*per:raise ValueError('canonical slice offset/bytes')

def inspect(root,tensors):
    root=Path(root);seen=set();manifest={}
    if tuple((root/'phases.txt').read_text().splitlines())!=PHASES:raise ValueError('phase schedule')
    for row in csv.DictReader((root/'index.tsv').open(),delimiter='\t'):
        key=(row['phase'],int(row['layer']),row['name'])
        if key in seen or key[0] not in PHASES or not 0<=key[1]<36 or key[2] not in STAGES:raise ValueError('unknown/duplicate state')
        seen.add(key);p=root/row['file']
        if p.parent!=root or not p.is_file():raise ValueError('payload path')
        data=p.read_bytes();payload(row,data);manifest[p.name]=hashlib.sha256(data).hexdigest()
    expected={(p,l,s) for p in PHASES for l in range(36) for s in STAGES}
    if seen!=expected:raise ValueError('incomplete native 36-layer7-phase6-state boundary')
    byte_keys=set()
    for row in csv.DictReader((root/'byte_checks.tsv').open(),delimiter='\t'):
        byte_entry(row,tensors);key=(int(row['layer']),int(row['component']),int(row['expert']))
        if key in byte_keys:raise ValueError('duplicate bytecheck');
        byte_keys.add(key)
    if {(l,k) for l,k,e in byte_keys}!={(l,k) for l in range(36) for k in range(6)}:raise ValueError('incomplete expert/bias verification')
    for phase in ('prefill_final','decode0','decode1','decode7','decode31'):
        p=root/(phase+'.logits.f32');data=p.read_bytes()
        if len(data)!=201088*4 or any(not math.isfinite(v[0]) for v in struct.iter_unpack('<f',data)):raise ValueError('logits count/finite')
        manifest[p.name]=hashlib.sha256(data).hexdigest()
    return {'status':'PASS_NATIVE_BOUNDARY','numeric_states':36*7,'selected_state_payloads':len(seen),'five_full_logit_rows':5,'canonical_component_slices':len(byte_keys),'payload_sha256':manifest}

def compare(a,b):
    if a['payload_sha256']!=b['payload_sha256']:raise ValueError('same-profile repeated state/logit mismatch')
    return {'status':'SAME_PROFILE_BITWISE_PASS','numeric_states':252,'full_logits':5,'scope':'native upstream189+32, selected FFN states; no cross-profile equality'}
