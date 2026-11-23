"""Lossless sample service investment gate; no inference latency promotion."""
import argparse,json,math,statistics
from pathlib import Path
from run_bounded import sha256
SLAB=4406400

def inspect(path,arm):
    v=json.loads(Path(path).read_text())
    if v.get('status')!='PASS_LOSSLESS_SAMPLE_SERVICE' or v.get('arm')!=arm or v.get('component_checks')!=384 or v.get('source_fd_direct')is not True or v.get('pack_fd_direct')is not True:
        raise ValueError('full sample bytes/direct provenance missing')
    for k in ['memory_alignment','offset_alignment']:
        a=v.get(k)
        if type(a)is not int or a<=0 or a>1024*1024:raise ValueError('invalid verified alignment')
    rows=v.get('reports',[])
    if len(rows)!=2 or [x.get('tier') for x in rows]!=['CPU','GPU']:raise ValueError('both tiers required in order')
    for x in rows:
        if x.get('experts_served')!=256 or x.get('logical_weight_bytes')!=256*3*SLAB or x.get('pread_calls')!=(768 if arm=='A' else 256) or x.get('destination_verified')is not True or x.get('destination_shape')!=[2880,2880]:raise ValueError('fixed work/destination/counts differ')
        if type(x.get('aligned_request_bytes'))is not int or x['aligned_request_bytes']<x['logical_weight_bytes']:raise ValueError('request byte accounting invalid')
        t=x.get('service_s')
        if type(t)not in (int,float) or not math.isfinite(t) or t<=0:raise ValueError('nonfinite/missing/zero service time')
    return v

def inspect_pack(path,spec_path):
    import re
    v=json.loads(Path(path).read_text());spec=json.loads(Path(spec_path).read_text())
    if v.get('status')!='PACK_CREATED_BYTES_NOT_YET_QUALIFIED' or v.get('source_fd_direct')is not True or len(v.get('experts',[]))!=64:raise ValueError('producer contract')
    for k,value in spec.items():
        if k!='experts' and v.get(k)!=value:raise ValueError('source specification changed')
    alignment=v.get('alignment');stride=v.get('stride');window=v.get('weight_window')
    if type(alignment)is not int or alignment<=0 or alignment>1048576 or type(stride)is not int or stride<=0 or stride%alignment or type(window)is not int or window<3*SLAB or window%alignment:raise ValueError('pack alignment contract')
    logical=0
    for n,(a,b) in enumerate(zip(spec['experts'],v['experts'])):
        if any(b.get(k)!=a[k] for k in ['layer','expert','tier']) or b.get('pack_offset')!=n*stride or len(b.get('components',[]))!=6:raise ValueError('expert identity/offset')
        for k,(original,packed) in enumerate(zip(a['components'],b['components'])):
            if any(packed.get(key)!=value for key,value in original.items()):raise ValueError('canonical component changed')
            relative=k*SLAB if k<3 else window+(k-3)*11520
            if packed.get('packed_relative_offset')!=relative or relative+packed['size_bytes']>stride or not re.fullmatch('[0-9a-f]{64}',packed.get('sha256','')):raise ValueError('component packing/hash')
            logical+=packed['size_bytes']
    if logical!=v.get('logical_bytes') or v.get('pack_bytes')!=64*stride or not 0<v['pack_bytes']<=2*1024**3 or Path(v['pack_path']).stat().st_size!=v['pack_bytes'] or not re.fullmatch('[0-9a-f]{64}',v.get('pack_sha256_write_stream','')):raise ValueError('pack full size/stream hash')
    return {'status':'PASS_PRODUCER_INDEX_CONTRACT_READBACK_PENDING','components':384,'logical_bytes':logical,'pack_bytes':v['pack_bytes'],'pack_sha256_write_stream':v['pack_sha256_write_stream'],'readback':'NOT_RUN until four service arms revalidate every component against C211 canonical source'}

def evaluate(directory):
    d=Path(directory);p=json.loads((d/'protocol.json').read_text());runs=p['runs']
    if len(runs)!=4 or [r['arm'] for r in runs]!=['A','B','B','A'] or len({r['id'] for r in runs})!=4:raise ValueError('frozen ABBA cardinality/IDs required')
    rows=[inspect(r['result_path'],r['arm']) for r in runs];reports={}
    for tier_index,tier in enumerate(['CPU','GPU']):
        pairs=[]
        for a,b in [(0,1),(3,2)]:
            ref=rows[a]['reports'][tier_index]['service_s'];candidate=rows[b]['reports'][tier_index]['service_s']
            pairs.append({'arms':[runs[a]['id'],runs[b]['id']],'reference_s':ref,'candidate_s':candidate,'gain_percent':100*(ref-candidate)/ref})
        med=statistics.median(x['gain_percent'] for x in pairs)
        reports[tier]={'pairs':pairs,'median_paired_gain_percent':med,'service_15_percent_gate':med>=15 and all(x['gain_percent']>0 for x in pairs)}
    combined=[]
    for a,b in [(0,1),(3,2)]:
        ref=sum(x['service_s'] for x in rows[a]['reports']);candidate=sum(x['service_s'] for x in rows[b]['reports'])
        combined.append({'arms':[runs[a]['id'],runs[b]['id']],'reference_s':ref,'candidate_s':candidate,'gain_percent':100*(ref-candidate)/ref})
    combined_gain=statistics.median(x['gain_percent'] for x in combined)
    service_gate=combined_gain>=15 and all(x['gain_percent']>0 for x in combined)
    cases=p['projection']['C280_R0_cases']
    if set(cases)!={'nominal153','code153'}:raise ValueError('two frozen projection cases required')
    projections={}
    for case,evidence in p['projection']['C280_R0_cases'].items():
        # Fixed logical load mix is only a scenario: historical counts include both phases.
        # Callback wait contains one output-row prefill callback; it is optimistic for decode.
        c,g=evidence['CPU_generations'],evidence['GPU_generations'];fraction=evidence['optimistic_normal_wait_decode_fraction']
        if any(type(v)is not int or v<=0 for v in [c,g]) or type(fraction)not in (int,float) or not math.isfinite(fraction) or not 0<fraction<=1:raise ValueError('projection counts/fraction invalid')
        gains=[]
        for a,b in [(0,1),(3,2)]:
            ref=c*rows[a]['reports'][0]['service_s']+g*rows[a]['reports'][1]['service_s']
            candidate=c*rows[b]['reports'][0]['service_s']+g*rows[b]['reports'][1]['service_s']
            gains.append(100*(ref-candidate)/ref)
        gain=statistics.median(gains);projection=evidence['optimistic_normal_wait_decode_fraction']*gain
        projections[case]={'estimated_service_gain_percent':gain,'optimistic_decode_projection_percent':projection,'tier_sensitivity_percent':{tier:evidence['optimistic_normal_wait_decode_fraction']*r['median_paired_gain_percent'] for tier,r in reports.items()}}
    opportunity=any(x['optimistic_decode_projection_percent']>=10 for x in projections.values())
    engineering=p['projection']['integration_engineering_h']
    if type(engineering)not in (int,float)or not math.isfinite(engineering)or not 0<engineering<=12:raise ValueError('engineering bound not admissible')
    passed=service_gate and opportunity
    return {'status':'GO_LAYOUT_INTEGRATION_INVESTMENT' if passed else 'NO_GO_LAYOUT_SERVICE_INVESTMENT','tiers':reports,'combined_serial_service':{'pairs':combined,'median_paired_gain_percent':combined_gain,'15_percent_gate':service_gate},'critical_projection':projections,'projection_class':'ESTIMADO_CONDITIONED_SCENARIO; observed normal callback wait scaled by logical load mix/service, one prefill output-row wait included, no compute contention/wake-tail attribution. Not formal bound or target speedup','scope':'64 expert lossless sample, four persistent workers, native CPU/CUDA bytes-ready destination; no Transformer compute','engineering_estimate_h':engineering,'inference_speedup':'NOT_RUN','full_pack':'ADMITTED_ONLY_IF_GO_AND_LIVE_STORAGE','next':'One isolated integrated canary required to resolve critical projection and contention before performance claims'}

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('directory',type=Path);a.add_argument('--arm',choices=['A','B']);a.add_argument('--pack-spec',type=Path);a.add_argument('--output',type=Path,required=True);v=a.parse_args();r=inspect_pack(v.directory,v.pack_spec) if v.pack_spec else inspect(v.directory,v.arm) if v.arm else evaluate(v.directory)
    with v.output.open('x')as f:json.dump(r,f,indent=2,allow_nan=False);f.write('\n')
    print(r['status'])
