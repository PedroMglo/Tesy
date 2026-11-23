#!/usr/bin/env python3
"""P14 same-profile OFF/ON/OFF logits and capture schema gate."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

from c2_gate import GateError,strict_json
import c7_boundary_gate as c7
from run_bounded import sha256

ARMS=(('c63-p14-off01','P14-observer-off','tools/c63_profile_probe'),
      ('c63-p14-on01','P14-observer-on','tools/c63_boundary_capture'),
      ('c63-p14-off02','P14-observer-off-repeat','tools/c63_profile_probe'))


def numeric_ids(path):
    selected=next((row.split('\t') for row in path.read_text().splitlines()
                   if row.startswith('log_medium\t')),None)
    if not selected or len(selected)!=3:
        raise GateError('frozen numeric IDs missing')
    prompt,continuation=selected[1].split(','),selected[2].split(',')
    if len(prompt)!=189 or len(continuation)!=43:
        raise GateError('frozen numeric ID count changed')
    return prompt,continuation


def source(root,run_id,variant,binary,protocol):
    stem=root/'raw'/run_id
    manifest=strict_json(Path(str(stem)+'.json').read_text())
    if manifest['run_id']!=run_id or manifest['variant']!=variant or \
       manifest['command'][0]!=str(Path(binary).resolve()) or \
       manifest['binary_sha256']!=protocol['binaries_sha256'][Path(binary).name] or \
       manifest['backend_sha']!=protocol['backend_sha'] or \
       manifest['backend_libraries_sha256']!=protocol['backend_libraries_sha256'] or \
       manifest['mapped_backend_libraries_sha256']!=protocol['backend_libraries_sha256'] or \
       not manifest['mapped_libraries_match_ldd'] or \
       manifest['workload_sha256']!=protocol['numeric_ids_sha256'] or \
       manifest['artifact_identity']['stat_at_launch']!=protocol['model_stat'] or \
       manifest['artifact_identity']['stat_at_end']!=protocol['model_stat'] or \
       manifest['resource_authority']!=protocol['resources'] or \
       manifest['limits']['resource_protocol_sha256']!=sha256(root/'protocol.json') or \
       manifest['explicit_env']!={} or manifest['returncode']!=0 or \
       manifest['stop_reason'] is not None:
        raise GateError('P14 run identity/completion differs from freeze: '+run_id)
    for suffix,digest in manifest['output_sha256'].items():
        if sha256(Path(str(stem)+suffix))!=digest:
            raise GateError('P14 bounded raw hash changed')
    log=Path(str(stem)+'.stderr').read_text(errors='replace')
    placement={int(i):dev for i,dev in re.findall(
        r'load_tensors: layer\s+(\d+) assigned to device (CPU|CUDA0)',log)}
    if set(placement)!=set(range(37)) or any(
       placement[i]!=('CPU' if i<23 else 'CUDA0') for i in range(37)):
        raise GateError('P14 loader placement missing/changed')
    if 'MoE expert streaming uses O_DIRECT' not in log:
        raise GateError('P14 O_DIRECT load path not observed')
    return {'manifest_sha256':sha256(Path(str(stem)+'.json')),
            'elapsed_s':manifest['elapsed_s'],'maxima':manifest['maxima'],
            'mapped_libraries':manifest['mapped_backend_libraries_sha256'],
            'placement':placement}


def compare(root,protocol):
    ids=Path(protocol['numeric_ids_path'])
    if sha256(ids)!=protocol['numeric_ids_sha256']:
        raise GateError('numeric IDs changed')
    prompt,continuation=numeric_ids(ids)
    sources={}
    for run_id,variant,binary in ARMS:
        sources[run_id]=source(root,run_id,variant,binary,protocol)
    on_root=root/'raw'/(ARMS[1][0]+'.capture')
    on_logits,coverage=c7.capture(on_root)
    with (on_root/'byte_checks.tsv').open(newline='') as f:
        checks=list(csv.DictReader(f,delimiter='\t'))
    if not checks or any(row['status']!='EQUAL' for row in checks) or \
       not all(any(row['layer']==str(layer) and row['tensor']==str(kind)
                   for row in checks) for layer in (0,22,23,25,29,35)
                   for kind in range(6)):
        raise GateError('P14 active expert byte/lifetime witnesses incomplete')
    off=[]
    for run_id in (ARMS[0][0],ARMS[2][0]):
        stem=root/'raw'/run_id
        selected,seal=c7.off(stem,(prompt,continuation))
        off.append((selected,seal,Path(str(stem)+'.f32').read_bytes()))
    mismatch=[]
    if off[0][2]!=off[1][2]:
        left,right=off[0][2],off[1][2]
        first=next(i for i in range(0,len(left),4) if left[i:i+4]!=right[i:i+4])
        mismatch.append({'arm':'off02','phase':'all33','row':first//(4*c7.VOCAB),
                         'first_logit_index':(first//4)%c7.VOCAB})
    for phase in c7.LOGIT_PHASES:
        base=off[0][0][phase]
        if base!=on_logits[phase]:
            first=next(i for i in range(0,len(base),4)
                       if base[i:i+4]!=on_logits[phase][i:i+4])
            mismatch.append({'arm':'on01','phase':phase,'first_logit_index':first//4})
    return {'schema':'c63-p14-numeric-gate-v1',
            'status':'SAME_PROFILE_LOGITS_AND_CAPTURE_PASS' if not mismatch else
                     'FAIL_SAME_PROFILE_FIDELITY',
            'mismatch':mismatch,'coverage':coverage,'sources':sources,
            'off_all33_sha256':hashlib.sha256(off[0][2]).hexdigest(),
            'on_logits_sha256':{phase:hashlib.sha256(data).hexdigest()
                                for phase,data in on_logits.items()},
            'claim_limit':'250 routed numeric states captured; canonical resident layer reference and independent attention/KV not yet run'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    args=parser.parse_args()
    protocol=strict_json((args.root/'protocol.json').read_text())
    print(json.dumps(compare(args.root,protocol),sort_keys=True,allow_nan=False))


if __name__=='__main__':
    main()
