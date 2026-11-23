"""Fixed canonical sample and codec characterization; no production speed claim."""
import argparse,json,math,statistics
from pathlib import Path

def finite(v):
    return type(v) in (int,float) and math.isfinite(v) and v>0

def evaluate(value,index,pins):
    if value.get('schema')!='tesy-fixed-zstd-characterization-v1' or value.get('status')!='PASS_CANONICAL_LOSSLESS_CHARACTERIZATION':raise ValueError('missing complete characterization')
    fixed={'zstd_version':'1.5.7','compression_level':1,'checksum':True,'codec_workers':0,'component_count':384,'source_fd_direct':True}
    if any(value.get(k)!=v for k,v in fixed.items()):raise ValueError('frozen codec/reader contract')
    if value.get('mapped_codec_libraries_sha256')!=pins:raise ValueError('actual codec mapping identity')
    rows=value.get('components')
    expected=[(e,c) for e in index['experts'] for c in e['components']]
    if type(rows) is not list or len(rows)!=len(expected) or len(rows)!=384:raise ValueError('exact sample cardinality')
    grouped={};weights=[]
    for row,(e,c) in zip(rows,expected):
        fixed={'layer':e['layer'],'tier':e['tier'],'expert':e['expert'],'name':c['name'],'source_offset':c['source_offset'],'source_sha256':c['sha256'],'logical_bytes':c['size_bytes'],'exact_bytes':True}
        if any(row.get(k)!=v for k,v in fixed.items()):raise ValueError('source/strata/byte contract')
        n=row['logical_bytes'];size=row.get('encoded_bytes');a=value.get('offset_alignment')
        if type(a) is not int or not 0<a<=2**20 or type(size) is not int or not 0<size<=n+n//128+1024 or row.get('aligned_encoded_bytes')!=(size+a-1)//a*a:raise ValueError('bounded encoded size/alignment')
        times=row.get('decompress_to_ready_s')
        if type(times) is not list or len(times)!=4 or not all(finite(t) for t in times) or not finite(row.get('read_s')) or not finite(row.get('compress_s')):raise ValueError('all four finite complete codec timings')
        if n==4406400:
            s=row.get('substreams',{})
            if s.get('scale_bytes')!=259200 or s.get('qs_bytes')!=4147200 or len(s.get('scale_histogram',[]))!=256 or sum(s['scale_histogram'])!=259200:raise ValueError('MXFP4 inline exponent/qs decomposition')
            weights.append(row)
        grouped.setdefault(row['tier']+('/weight' if n==4406400 else '/bias'),[]).append(row)
    if value.get('logical_bytes')!=sum(r['logical_bytes'] for r in rows) or not finite(value.get('elapsed_s')):raise ValueError('total physical receipt')
    summary={}
    for group,rs in grouped.items():
        logical=sum(r['logical_bytes'] for r in rs);encoded=sum(r['encoded_bytes'] for r in rs);aligned=sum(r['aligned_encoded_bytes'] for r in rs)
        summary[group]={'components':len(rs),'logical_bytes':logical,'encoded_bytes':encoded,'aligned_encoded_bytes':aligned,'saved_logical_percent':100*(1-encoded/logical),'saved_aligned_percent':100*(1-aligned/logical),'decompress_ready_s_per_component_median':statistics.median(statistics.median(r['decompress_to_ready_s']) for r in rs),'ratio_min':min(r['aligned_encoded_bytes']/r['logical_bytes'] for r in rs),'ratio_max':max(r['aligned_encoded_bytes']/r['logical_bytes'] for r in rs)}
    ratio=min(r['aligned_encoded_bytes']/r['logical_bytes'] for r in weights)
    return {'status':'PASS_FIXED_CANONICAL_CODEC_CHARACTERIZATION','classification':'MEDIDO_NO_TARGET','groups':summary,'best_sample_weight_aligned_ratio':ratio,'conditional_zero_reconstruction_all_work_byte_service_upper_percent':100*(1-ratio),'integration_investment_threshold_percent':20,'scope':'Best sampled weight ratio hypothetically applies to every mandatory read, zero reconstruction/copy/CPU contention overhead; all work assumed byte-proportional. This generous conditional scenario is not a universal physical bound or measured target speedup. Biases are already resident and earn no per-expert I/O benefit.','unmeasured':'Compressed-store read service, target contention, unsampled expert ratios and integration. Actual reconstruction/copy cost reported independently; no codec runtime admitted without >=20% complete-path foundation.'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('receipt',type=Path);p.add_argument('index',type=Path);p.add_argument('protocol',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();receipt=json.loads(a.receipt.read_text());protocol=json.loads(a.protocol.read_text())
    if receipt.get('source_identity')!=protocol['model_stat']:raise ValueError('actual direct fd identity differs from frozen model')
    v=evaluate(receipt,json.loads(a.index.read_text()),protocol['codec_libraries_sha256'])
    with a.output.open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')
    print(v['status'])
