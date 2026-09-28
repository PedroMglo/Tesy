#!/usr/bin/env python3
"""Hash-checked C76b/C78 cgroup file-charge differential, without model rerun."""

import json
import math
from pathlib import Path

from c2_gate import GateError, strict_json
from c83_router_footprint import sha

ROOT = Path('results/c87-file-charge-differential-20260928T2022Z')
PARENTS = {
    'C76b': (Path('results/c76b-session-wave-boundary-20260928T1918Z'),
             'raw/c76b-p12-session-wave-on01.samples.jsonl'),
    'C78': (Path('results/c78-session-wave-repeat-20260928T1929Z'),
            'raw/c78-p12-session-wave-on-repeat01.samples.jsonl'),
}
GIB = 2**30


def parent(name):
    root, relative = PARENTS[name]
    protocol = strict_json((root/'protocol.json').read_text())
    manifest = strict_json((root/'manifest.json').read_text())
    decision = strict_json((root/'decision.json').read_text())
    path = root/relative
    listed = manifest['raw_sha256'].get(relative)
    if not listed or listed['sha256'] != sha(path) or listed['bytes'] != path.stat().st_size or \
       manifest['protocol_sha256'] != sha(root/'protocol.json'):
        raise GateError(f'{name} raw/manifest/protocol hash mismatch')
    samples = [strict_json(line) for line in path.read_text().splitlines()]
    if not samples:
        raise GateError(f'{name} empty samples')
    previous = -1
    for sample in samples:
        t = sample['elapsed_s']
        if type(t) not in (int,float) or not math.isfinite(t) or t < 0 or \
           not previous < t <= previous + 3 or sample['proc']['VmSwap'] != 0 or \
           sample['cgroup']['swap_current'] != 0:
            raise GateError(f'{name} invalid sample time/swap')
        previous = t
        for key, value in (('memory_current',sample['cgroup'].get('memory_current')),
                           ('memory_peak',sample['cgroup'].get('memory_peak')),
                           ('VmRSS',sample['proc'].get('VmRSS')),
                           ('read_bytes',sample['proc'].get('read_bytes'))):
            if type(value) is not int or value < 0:
                raise GateError(f'{name} missing/invalid {key}')
        if sample['cgroup']['memory_peak'] < sample['cgroup']['memory_current']:
            raise GateError(f'{name} peak below current')
        stat = sample['cgroup']['memory_stat']
        for key in ('anon','file','shmem','file_mapped'):
            if type(stat.get(key)) is not int or stat[key] < 0:
                raise GateError(f'{name} missing/invalid {key}')
        if stat['file'] < stat['shmem']:
            raise GateError(f'{name} file charge below shmem')
    return protocol, manifest, decision, samples


def row(sample):
    stat = sample['cgroup']['memory_stat']
    return {'elapsed_s':sample['elapsed_s'],
            'cgroup_current_bytes':sample['cgroup']['memory_current'],
            'cgroup_peak_bytes':sample['cgroup']['memory_peak'],
            'anon_bytes':stat['anon'],'file_bytes':stat['file'],
            'shmem_bytes':stat['shmem'],'file_mapped_bytes':stat['file_mapped'],
            'file_minus_shmem_bytes':stat['file']-stat['shmem'],
            'rss_bytes':sample['proc']['VmRSS'],
            'proc_read_bytes':sample['proc']['read_bytes'],
            'model_direct_fds':sample['model_fds']['direct'],
            'model_buffered_fds':sample['model_fds']['buffered']}


def nearest(samples, target):
    sample = min(samples,key=lambda sample:abs(sample['elapsed_s']-target))
    if abs(sample['elapsed_s']-target) > 0.75:
        raise GateError('C87 shared-time sample too far from target')
    return row(sample)


def analyze():
    a = parent('C76b');b = parent('C78')
    for key in ('backend_sha','binary_sha256','model_sha256_previously_verified',
                'model_stat','profile','call_plan'):
        if a[0][key] != b[0][key]:
            raise GateError(f'C76b/C78 profile differs: {key}')
    if a[2]['status'] != 'SAME_PROFILE_BITWISE_PASS_FULL_BOUNDARY' or \
       b[2]['status'] != 'FAIL_RESOURCES_OR_EVIDENCE' or \
       b[2]['failure_attribution'] != 'CGROUP_PREVENTIVE_MARGIN':
        raise GateError('parent gate statuses differ')
    timeline = {name:{str(t):nearest(parent_data[3],t) for t in (2,4,6,8,10,12,14)}
                for name,parent_data in (('C76b',a),('C78',b))}
    first,second=timeline['C76b']['14'],timeline['C78']['14']
    delta={key:second[key]-first[key] for key in
           ('cgroup_current_bytes','anon_bytes','file_bytes','shmem_bytes',
            'file_mapped_bytes','file_minus_shmem_bytes','rss_bytes')}
    result={'schema':'c87-file-charge-differential-v1',
            'evidence_class':'INFERIDO_FROM_HASH_VERIFIED_TELEMETRY',
            'parent_status':{'C76b':a[2]['status'],'C78':b[2]['status']},
            'same_backend_binary_model_profile_call_plan':True,
            'caps_bytes':{'C76b':a[0]['resources']['cgroup']['memory_max_bytes'],
                          'C78':b[0]['resources']['cgroup']['memory_max_bytes']},
            'sample_counts':{'C76b':len(a[3]),'C78':len(b[3])},
            'timeline':timeline,'at_14s_delta_C78_minus_C76b_bytes':delta,
            'C78_last_sample':row(b[3][-1]),
            'C78_terminal_peak_bytes':b[2]['evidence']['maxima']['cgroup_peak_bytes'],
            'C78_capture_bytes':b[2]['evidence']['capture_bytes'],
            'source_sha256':{name:{'samples':m['raw_sha256'][relative]['sha256'],
                                     'protocol':sha(root/'protocol.json'),
                                     'decision':sha(root/'decision.json')}
                             for name,(root,relative),m in
                             [('C76b',PARENTS['C76b'],a[1]),('C78',PARENTS['C78'],b[1])]},
            'interpretation':'C78 file charge grew after anon stabilized while C76b file charge stayed lower; the source of those file pages and their reclaimability are not identified by these counters.',
            'limits':['C78 stopped before complete capture; no numeric comparison from C78',
                      'memory.stat file includes shmem and other file-backed charge, not an inode attribution',
                      'different envelope and external host conditions can change reclaim behavior',
                      'the raw capture payload size is too small to explain the full file-charge delta by itself',
                      'do not change the C78 guard or relabel its FAIL']}
    return result


def main():
    if not ROOT.is_dir():
        raise GateError('C87 root missing')
    result=analyze()
    with (ROOT/'analysis.json').open('x') as stream:
        json.dump(result,stream,indent=2,sort_keys=True,allow_nan=False)
        stream.write('\n')
    delta=result['at_14s_delta_C78_minus_C76b_bytes']
    print(json.dumps({'status':'ANALYSIS_ONLY','file_delta_gib':delta['file_bytes']/GIB,
                      'anon_delta_gib':delta['anon_bytes']/GIB}))


if __name__ == '__main__':
    main()
