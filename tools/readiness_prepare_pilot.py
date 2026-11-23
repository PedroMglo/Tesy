"""One frozen isolated pilot; original bounded runner and original loader libraries."""
import json,os,hashlib,struct
from pathlib import Path
from c152_journal_validate import validate
from c152_snapshot_read import snapshot
from epoch_accounting import Epoch
from run_bounded import sha256,backend_library_hashes
from host_resource_policy import validate_resource_protocol
from parallel_runtime import parallel_environment

repo=Path(__file__).resolve().parents[1]
ep=repo/'results/c232-post-c231-readiness-20261001T180602Z';out=repo/'results/c234-readiness-pilot-or-bound-20261001'
original=repo/'results/c233-readiness-native-operator-20261001';base=json.loads((original/'protocol.json').read_text())
capture=repo/'results/c127-slots40-numeric-20260929T1654Z/raw/c127-slots40-on01.capture'
trace_root=repo/'results/c163-instrumentation-overhead-20260930T1145Z/raw'
initial=snapshot(trace_root/'c163-on-1.capture/before-warm.snap')
snap=snapshot(trace_root/'c163-on-1.capture/after-prefill.snap')
events=validate(trace_root/'c163-on-1.trace.window.trace',initial=initial)['rows']
observed=json.loads((ep/'readiness-existing.json').read_text())['cases'][0]['rows']
cases=[]
for name,layer,predicate in [('all-hit',12,lambda n:n==0),('mixed',24,lambda n:0<n<4),('all-absent',0,lambda n:n==4)]:
    row=next(r for r in observed if r['layer']==layer and predicate(r['misses']))
    demands=[e for e in events if e['call_id']==row['call'] and e['layer']==layer and e['kind']=='DEMAND']
    assert len(demands)==4 and sum(d['state']!=2 for d in demands)==row['misses']
    # Only the ordered miss pattern transfers. Activations/IDs are explicitly C127 decode0.
    cases.append({'name':name,'operator_layer':layer,'activation_origin':'C127 ON decode0',
        'trace_origin':'C163-on1 slots44 C-API','trace_call':row['call'],
        'trace_experts':row['experts'],'trace_slots':row['slots'],
        'miss_mask':[d['state']!=2 for d in demands],
        'selection':'first structural match in validated decode47 trace, not selected by pilot timings',
        'native_components':next(l['components'] for l in snap['layers'] if l['layer']==layer)})
with (out/'cases.json').open('x') as f:json.dump({'cases':cases,'scope':'Trace-derived positional miss masks applied to C127 selected activations/IDs. Not exact replay of C163 routing/compute.','schedule':'ABBAABBA','pairs':[[0,1],[3,2],[4,5],[7,6]]},f,indent=2);f.write('\n')
for filename in ('resource-policy.json','snapshot.json'):
    with (out/filename).open('x') as f:f.write((original/filename).read_text())
binary=out/'build/readiness_pilot';backend=Path(base['backend_root'])
files={str(binary):sha256(binary),str(out/'build/ggml-cpu-readiness.o'):sha256(out/'build/ggml-cpu-readiness.o')}
for p in ['tools/readiness_pilot.cpp','tools/readiness_pilot_state.h','tools/readiness_prepare_native_hook.py','tools/readiness_native_hook_fixture.cpp','tools/readiness_prepare_pilot.py','tools/c7_layer_reference.cpp','tools/c210_direct_reader.h','tools/residency_unit_run.py','tools/run_bounded.py']:
    files[str(repo/p)]=sha256(repo/p)
for path in backend_library_hashes(binary,backend):files[str(backend/path)]=sha256(backend/path)
for path,h in base['file_sha256'].items():
    if str(capture) in path and ('decode0_' in path or path.endswith('index.tsv')):files[path]=h
for path in [out/'cases.json',out/'native-hook-build.json',trace_root/'c163-on-1.capture/after-prefill.snap',trace_root/'c163-on-1.trace.window.trace']:
    files[str(path)]=sha256(path)
parallel=parallel_environment(os.environ);assert 'GOMP_SPINCOUNT' not in parallel['values']
projection=dict(base['cap_projection']);projection['worker_staging_bound_bytes']=4*(4406400+8192)
assert sum(v for k,v in projection.items() if k!='preventive_cgroup_guard_bytes')<base['resources']['cgroup']['memory_stop_bytes']
p={**{k:base[k] for k in ('epoch_path','model_path','model_id','model_stat','model_sha256_previously_verified','backend_root','backend_commit','resources','limits','common_env','start_inventory')},
    'schema':'readiness-native-pilot-v1','campaign_id':'c234-readiness-pilot','execution_scope_unit':'tesy-c234-readiness-pilot',
    'physical_envelope_s':210,'raw_projection_bytes':16*2**20,
    'claim_scope':'Isolated per-slot readiness in first gate MMID, original C75 CPU arithmetic/native loader; transferred miss patterns only; no Transformer/tokens/CUDA compute',
    'success_status':'MEASURED_ISOLATED_NATIVE_READINESS_PILOT_SELECTED_SCOPE','file_sha256':files,'cap_projection':projection,
    'runs':[{'id':'c234-pilot','variant':'collective-vs-native-slot-consumption','label':'retained-selected-pages-direct-loader','inventory':True,'timeout_s':120,'env':{},'command':[str(binary),base['model_path'],str(capture),str(out/'cases.json')]}],
    'arithmetic':'Single original C75 CPU C object copied/compiled with original flags and one consumer callback. Shared runtime/backend unchanged. All initial and repeated FFNs must bitwise match C127 ON; finite; component bytes direct-witnessed outside timing.',
    'lifetime':'No remap/eviction/reservation while graph consumers run. Immutable expert/slot/generation tags, keep pins until all consumers and native worker claimed flags finish. Fast acquire flag follows lock-protected native RESIDENT publication.',
    'schedule':'all-hit/mixed/all-absent; one declared native load and numeric validation per case; eight repetitions ABBAABBA. Same authoritative captured IDs/loads both arms, actual four native I/O workers. Not reordered expert FFN.',
    'timing':'Reserve/enqueue + wait or per-slot wait + whole original FFN, synchronized. Canonical readback/witness outside timing within envelope. No synthetic delays used for benefit.',
    'economic_gate_percent':5,'all_hit_max_regression_percent':5,
    'next_gate':'Correctness and all-hit <=5% regression AND net conditional opportunity >=5% full decode required for integration-design GO. Isolated gain does not certify production speedup.',
    'parallel_environment':parallel,'full_model_inference_authorized_s':0,'no_CUDA_operator':True,'no_retries':True,'publication':'LOCAL_ONLY'}
validate_resource_protocol(p)
assert Epoch(ep).budget(225,16*2**20)['admitted']
with (out/'protocol.json').open('x') as f:json.dump(p,f,indent=2,allow_nan=False);f.write('\n')
with (out/'admission.json').open('x') as f:json.dump(Epoch(ep).budget(225,16*2**20),f,indent=2);f.write('\n')
print(json.dumps({'cases':[(c['name'],c['trace_call'],c['miss_mask']) for c in cases],'envelope_s':210,'cap_bytes':p['resources']['cgroup']['memory_max_bytes']}))
