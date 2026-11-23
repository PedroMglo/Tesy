"""Reanalyse recorded counters with contained/cross-boundary sampling bounds."""
import csv, hashlib, json, subprocess
from pathlib import Path

STAT = ('file','anon','shmem','pgfault','pgmajfault','workingset_refault_file',
        'pgscan','pgsteal','pgscan_direct','pgsteal_direct','pgscan_kswapd','pgsteal_kswapd')

def counters(s):
    cg=s['cgroup'];out={}
    for label in ('events','events_local'):
        for k,v in cg.get(label,{}).items():out[label+'.'+k]=v
    for k in STAT:
        if k in cg['memory_stat']:out['stat.'+k]=cg['memory_stat'][k]
    for label,d in cg.get('pressure',{}).items():
        out['psi.'+label+'.total_us']=d['total']
    for k in ('read_bytes','rchar','syscr'):
        if k in s['proc']:out['proc.'+k]=s['proc'][k]
    return out

def phase(samples,label,begin,end,authority):
    intervals=[]
    for a,b in zip(samples,samples[1:]):
        # Widen each observed endpoint for collection latency, no interpolation.
        lo=a['elapsed_s']-a['collection_s'];hi=b['elapsed_s']+b['collection_s']
        if hi < begin or lo > end:continue
        ca,cb=counters(a),counters(b)
        delta={k:cb[k]-ca[k] for k in ca.keys()&cb.keys()}
        intervals.append(dict(begin=lo,end=hi,contained=lo>=begin and hi<=end,delta=delta))
    keys=set(k for x in intervals for k in x['delta']);bounds={}
    for k in sorted(keys):
        if k.startswith('stat.') and k.split('.')[1] in ('file','anon','shmem'):continue
        ds=[x['delta'].get(k,0) for x in intervals]
        if any(v<0 for v in ds):bounds[k]={'status':'COUNTER_REGRESSION_OR_GAUGE','deltas':ds};continue
        bounds[k]={'lower':sum(x['delta'].get(k,0) for x in intervals if x['contained']),
                   'upper':sum(ds)}
    selected=[s for s in samples if begin<=s['elapsed_s']<=end]
    return dict(phase=label,begin_s=begin,end_s=end,duration_s=end-begin,
        boundary_authority=authority,intervals=intervals,counter_delta_bounds=bounds,
        observations=[{k:s.get(k) for k in ('elapsed_s','proc','mem_available_bytes','gpu','thermal','resource_observation')}|
            {'cgroup':{k:s['cgroup'].get(k) for k in ('memory_current','memory_peak','memory_high','memory_max','swap_current')},
             'stat_gauges':{k:s['cgroup']['memory_stat'].get(k) for k in ('file','anon','shmem')}} for s in selected],
        limitations='Counters sampled sequentially; widened collection intervals are conservative sampling bounds, not exact per-op attribution. PSI some/full not summed; IO counters/faults not physical NVMe bytes.')

def run(root,out):
    out.mkdir(exist_ok=False)
    c182=root/'results/c182-mmap-retained-prefix-20260930T1601Z/raw'
    raw=json.loads((c182/'c182-prefix.json').read_text());item=raw['results'][0]
    samples=[json.loads(l) for l in (c182/'c182-prefix.samples.jsonl').read_text().splitlines()]
    start,end=item['started_s'],item['ended_s'];p=item['timings']['prompt_ms']/1000;d=item['timings']['predicted_ms']/1000
    phases=[phase(samples,'readiness',0,raw['preflight']['ready_elapsed_s'],'client ready elapsed'),
            phase(samples,'request_first_forward_work',start,end,'client request bounds; no observer, no overlapping request'),
            phase(samples,'prefill_approx',start,start+p,'INFERRED contiguous backend prompt_ms anchored to client start; exact backend transition timestamp NOT_RECORDED'),
            phase(samples,'decode_approx',start+p,end,'INFERRED remaining request; exact native transition NOT_RECORDED')]
    exposure=phases[1]['counter_delta_bounds']['events.high']['lower']>0
    env=raw['preflight']['relevant_environment'];assert env=={'LD_LIBRARY_PATH':str(root/'backends/c165-mmap-diagnostic/build-diagnostic/bin'),'TESY_MMAP_NO_PREFETCH':'1'}
    assert all(s['cgroup']['memory_high']==20937965568 and s['cgroup']['memory_max']==21474836480 for s in samples)
    c166=root/'results/c166-mmap-phase-diagnostic-20260930T1230Z/raw';r=json.loads((c166/'c166-none.json').read_text());l=json.loads((c166/'c166-none.launch.json').read_text());origin=l['start_inventory']['popen_invoked_monotonic_ns']/1e9
    ss=[json.loads(x) for x in (c166/'c166-none.samples.jsonl').read_text().splitlines()]
    native=[]
    for row in csv.DictReader((c166/'none.capture/phase-timing.tsv').open(),delimiter='\t'):
        native.append(phase(ss,row['phase'],int(row['begin_us'])/1e6-origin,int(row['end_us'])/1e6-origin,'CLOCK_MONOTONIC native microseconds relative to Popen marker; sample elapsed rounded1ms and collector span retained'))
    for x in phases+native:
        # Interval deltas compact; retain observed counters separately in original raw.
        x.pop('intervals')
    result={'status':'HIGH_EXPOSURE_FORWARD_CONFIRMED' if exposure else 'NOT_RUN_NO_HIGH_EXPOSURE','C182':phases,'C166_NONE':native,
        'C182_accounting':{'official_ids':78,'reported_outputs':item['usage']['completion_tokens'],'predicted_n':item['timings']['predicted_n'],'rate_times_duration':d*item['timings']['predicted_per_second'],'source_steps':'server-common.h:n_gen_steps=n_gen-1','prefill_plus_decode_s':p+d,'client_request_s':end-start,'peak_above_high_mib':(max(s['cgroup']['memory_peak'] for s in samples)-20937965568)/2**20},
        'H1_CPU_compute':'UNKNOWN native CPU seconds/stacks not captured',
        'H2_IO_page_refault':'Observed faults/read_bytes/refaults; exclusive physical traffic/time UNKNOWN',
        'H3_high_reclaim':'Observed high during forwards; causal removable wall UNKNOWN; admits one intervention',
        'H4_mixed':'Current causal attribution UNKNOWN; A/B may narrow only declared scope',
        'C182_identity':{'executable':raw['preflight']['config']['server_command'][0],'environment':env,'libraries':raw['preflight']['actually_loaded_backend_libraries_sha256'],'observer':'absent on server; VERIFY only mmap_phase_probe'},
        'CPU52_GPU44':'C164 preserved POLICY_NO_GO_TESTED_SCOPE; no tuning'}
    (out/'reanalysis.json').write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
    import sys
    r=run(Path.cwd(),Path(sys.argv[1]));print(r['status'],r['C182_accounting'])
