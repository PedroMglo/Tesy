"""Integral lossless store admission/readback contracts, independent of performance."""
import argparse,json,re
from pathlib import Path
from run_bounded import sha256

def validate_index(path,spec_path):
    v=json.loads(Path(path).read_text());s=json.loads(Path(spec_path).read_text())
    if v.get('status')!='PACK_CREATED_BYTES_NOT_YET_QUALIFIED' or v.get('store_scope')!='INTEGRAL_GPT_OSS120B_36x128' or v.get('source_fd_direct')is not True:raise ValueError('integral producer scope/direct')
    if len(v.get('experts',[]))!=4608 or len(s.get('experts',[]))!=4608:raise ValueError('integral cardinality')
    for k,a in s.items():
        if k!='experts' and v.get(k)!=a:raise ValueError('source specification changed')
    stride=v.get('stride');a=v.get('alignment');window=v.get('weight_window')
    if type(a)is not int or not 0<a<=1048576 or type(stride)is not int or stride%a or stride<=0 or type(window)is not int or window%a or window<13219200:raise ValueError('alignment/stride')
    logical=0
    for n,(expected,actual) in enumerate(zip(s['experts'],v['experts'])):
        if expected['layer']!=n//128 or expected['expert']!=n%128 or any(actual.get(k)!=expected[k] for k in ['layer','expert','tier']) or actual.get('pack_offset')!=n*stride or len(actual.get('components',[]))!=6:raise ValueError('expert mapping/cardinality')
        for k,(c,r) in enumerate(zip(expected['components'],actual['components'])):
            if any(r.get(key)!=value for key,value in c.items()) or not re.fullmatch('[0-9a-f]{64}',r.get('sha256','')):raise ValueError('component metadata/hash')
            relative=k*4406400 if k<3 else window+(k-3)*11520
            if r.get('packed_relative_offset')!=relative or relative+r['size_bytes']>stride:raise ValueError('component bounds/layout')
            logical+=r['size_bytes']
    if v.get('logical_bytes')!=logical or v.get('pack_bytes')!=stride*4608 or not 0<v['pack_bytes']<=80*1024**3 or Path(v['pack_path']).stat().st_size!=v['pack_bytes'] or not re.fullmatch('[0-9a-f]{64}',v.get('pack_sha256_write_stream','')):raise ValueError('store size/full-stream SHA')
    return {'status':'PASS_INTEGRAL_PRODUCER_INDEX','component_count':27648,'expert_count':4608,'logical_bytes':logical,'pack_bytes':v['pack_bytes'],'pack_sha256_write_stream':v['pack_sha256_write_stream'],'readback':'PENDING'}

def validate_readback(path,index_path):
    r=json.loads(Path(path).read_text());v=json.loads(Path(index_path).read_text())
    if r.get('status')!='PASS_FULL_CANONICAL_PACK_READBACK' or r.get('component_checks')!=27648 or r.get('logical_bytes')!=v['logical_bytes'] or r.get('source_fd_direct')is not True or r.get('pack_fd_direct')is not True or r.get('pack_sha256_write_stream')!=v['pack_sha256_write_stream']:raise ValueError('integral bytes/readback not qualified')
    return {'status':'PASS_INTEGRAL_STORE_BYTES','component_count':27648,'original_gguf_sha256':'PREVIOUSLY_VERIFIED_NO_NEW_WHOLE_MODEL_REHASH','index_sha256':sha256(Path(index_path)),'pack_sha256_write_stream':v['pack_sha256_write_stream'],'scope':'All components compared against original canonical C211 bytes; no profile/kernel/latency claim'}
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('path',type=Path);a.add_argument('--spec',type=Path);a.add_argument('--index',type=Path);a.add_argument('--output',type=Path,required=True);v=a.parse_args()
    r=validate_index(v.path,v.spec) if v.spec else validate_readback(v.path,v.index)
    with v.output.open('x')as f:json.dump(r,f,indent=2,allow_nan=False);f.write('\n')
    print(r['status'])
