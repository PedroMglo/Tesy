"""Freeze an isolated operator family for the existing bounded runner."""
import json, os
from pathlib import Path
from epoch_accounting import Epoch
from host_resource_policy import freeze_protocol_resource_limits, validate_resource_protocol
from run_bounded import backend_library_hashes, sha256, file_identity
from parallel_runtime import parallel_environment

repo=Path(__file__).resolve().parents[1]
ep=repo/'results/c232-post-c231-readiness-20261001T180602Z'
out=repo/'results/c233-readiness-native-operator-20261001'
assert not (out/'protocol.json').exists(), 'no replacement freeze'
out.mkdir(exist_ok=True);(out/'raw').mkdir(exist_ok=True);(out/'.gitignore').write_text('raw/\n')
policy=json.loads((ep/'resource-policy.json').read_text())
if not (out/'resource-policy.json').exists():(out/'resource-policy.json').write_text(json.dumps(policy,indent=2)+'\n')
assert json.loads((out/'resource-policy.json').read_text())==policy
if not (out/'snapshot.json').exists():(out/'snapshot.json').write_text((ep/'snapshot.json').read_text())
model=Path('/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf')
backend=Path('/tmp/tesy-c75-backend-20260928');binary=ep/'build/readiness_operator'
capture=repo/'results/c127-slots40-numeric-20260929T1654Z/raw/c127-slots40-on01.capture'
resources=freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=2*2**30)
files={str(binary):sha256(binary)}
for f in ['tools/readiness_operator.cpp','tools/c7_layer_reference.cpp','tools/c210_direct_reader.h','tools/readiness_feasibility.py','tools/readiness_prepare_operator.py','tools/residency_unit_run.py','tools/run_bounded.py']:
    files[str(repo/f)]=sha256(repo/f)
for f in backend_library_hashes(binary,backend):files[str(backend/f)]=sha256(backend/f)
for f in capture.iterdir():
    if f.is_file() and (f.name=='index.tsv' or any(f.name.startswith(f'decode{phase}_{layer}_') for phase in (0,1,7,31) for layer in (0,12,24))):files[str(f)]=sha256(f)
parallel=parallel_environment(os.environ);assert 'GOMP_SPINCOUNT' not in parallel['values']
projection={'pool_max_bytes':3*44*4406400+3*128*11520,'graph_metadata_bound_bytes':32*2**20,'workspace_bound_bytes':64*2**20,'reader_and_comparison_bound_bytes':16*2**20,'libraries_and_misc_estimate_bytes':128*2**20,'uncertainty_bytes':512*2**20}
assert sum(projection.values())<resources['cgroup']['memory_stop_bytes']
projection['preventive_cgroup_guard_bytes']=resources['cgroup']['memory_stop_bytes']
p={'schema':'readiness-native-operator-feasibility-v1','campaign_id':'c233-readiness-native-operator','epoch_path':str(ep.relative_to(repo)),'execution_scope_unit':'tesy-c233-readiness-operator','physical_envelope_s':450,'raw_projection_bytes':16*2**20,'claim_scope':'Isolated CPU C127 decode states, original40 and44 pool metadata; first gate_MMID/fullFFN resident and direct reload timing; no Transformer/tokens/GPU compute','success_status':'MEASURED_NATIVE_CPU_OPERATOR_SELECTED_SCOPE','model_path':str(model),'model_id':'gpt-oss-120b-mxfp4-gguf','model_stat':file_identity(model),'model_sha256_previously_verified':'582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d','backend_root':str(backend),'backend_commit':'27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5','file_sha256':files,'resources':resources,'limits':{},'common_env':{'TESY_CPU_WAVE_SKIP_PARKED':'1'},'start_inventory':{'schema':'c120-start-inventory-v1','duration_s':60,'max_age_s':3,'policy_sha256':sha256(out/'resource-policy.json')},'runs':[{'id':f'c233-layer{i}','label':f'cpu-layer{i}','variant':'first-MMID-and-fullFFN-original-CPU','inventory':True,'timeout_s':60,'env':{},'command':[str(binary),str(model),str(capture),str(i)]} for i in (0,12,24)],'numeric':'All selected decode0/1/7/31 fullFFN bitwise to C127 ON; firstgate bitwise to fullFFN gate; actual graph order gate/up/down; original36FFN chain reused, not rerun','timing':'Per40/44 pool and activation: one declared fullFFN validation,6 alternating first/full repetitions resident-hot and6 direct-selected-reload repetitions; readback/reload outside compute spans, inside envelope','selection_rule':'CPU positional strata low0/mid12/high24; all four published C127 decode snapshots, not selected by speedup; decode misses in C163/C164 only explanatory','economic_gate_percent':5,'cap_projection':projection,'parallel_environment':parallel,'publication':'LOCAL_ONLY','full_model_inference_authorized_s':0,'threads':8,'no_CUDA_operator':True,'no_retries':True,'next_action':'Per-origin first-op/fullFFN envelopes; only>=5% first-op plus implementable plan admits a separately frozen isolated CPU readiness pilot'}
validate_resource_protocol(p)
with (out/'protocol.json').open('x') as f:json.dump(p,f,indent=2);f.write('\n')
e=json.loads((ep/'epoch.json').read_text())
e['raw_roots']+= [str((out/'raw').relative_to(repo)),'results/c234-readiness-pilot-or-bound-20261001/raw']
(ep/'epoch.json').write_text(json.dumps(e,indent=2)+'\n')
future=repo/'results/c234-readiness-pilot-or-bound-20261001';future.mkdir();(future/'raw').mkdir();(future/'.gitignore').write_text('raw/\nbuild/\n')
admission=Epoch(ep).budget(465,16*2**20)
assert admission['admitted'],admission
with (out/'admission.json').open('x') as f:json.dump(admission,f,indent=2);f.write('\n')
print(json.dumps(admission))
