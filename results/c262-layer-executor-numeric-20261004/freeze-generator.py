import sys,json,subprocess,hashlib,shutil
from pathlib import Path
sys.path.insert(0,'tools')
from epoch_accounting import Epoch
from host_resource_policy import freeze_protocol_resource_limits
from run_bounded import sha256,file_identity,backend_library_hashes
from c94_session_wave_8k_reference import tree_digest
root=Path.cwd();d=root/'results/c262-layer-executor-numeric-20261004';ep=root/'results/c236-post-c235-blocks-expert-reuse-20261004T105527Z';back=root/'backends/c262-layer-expert-reuse';build=ep/'build';lib=back/'build-c262-cuda/bin'
old=json.loads((root/'results/c260-expert-reuse-native-service-20261004/protocol.json').read_text());policy=json.loads((d/'resource-policy.json').read_text())
p={k:old[k] for k in ('epoch_path','model_path','model_id','model_stat','model_sha256_previously_verified','limits','parallel_runtime','publication')}
assert file_identity(Path(p['model_path']))==p['model_stat']
cap=20*2**30
# Whole previously observed peak retained, no subtraction of draft/RSS/file peaks.
projection={'previous_whole_observed_peak_bytes':16743944192,'source':'C258 raw cgroup memory_peak (maximum of whole envelopes, includes head conservatively)','capture_file_charge_bound_bytes':256*2**20,'extra_graph_metadata_bound_bytes':128*2**20,'workspace_transient_uncertainty_bytes':2*2**30,'additional_consumer_scratch_bound_bytes':16*2**20,'preventive_margin_bytes':512*2**20}
projection['projected_peak_bytes']=sum(v for k,v in projection.items() if type(v) is int and k!='preventive_margin_bytes');projection['preventive_stop_bytes']=cap-512*2**20
assert projection['projected_peak_bytes']<projection['preventive_stop_bytes']
p.update(schema='c262-private-layer-executor-fidelity-v1',campaign_id='c262-layer-executor-numeric',execution_scope_unit='tesy-c262-layer-executor-numeric',physical_envelope_s=1100,raw_projection_bytes=700*2**20,claim_scope='R0 unchanged selected bridge; R2 warm153 tiled FFN same-profile captured fidelity and six teacher-forced decode calls; no latency/general quality claim',success_status='PASS_PRIVATE_R0_BRIDGE_AND_R2_SELECTED_FIDELITY',backend_root=str(back),backend_commit=subprocess.check_output(['git','-C',str(back),'rev-parse','HEAD'],text=True).strip(),backend_tree=subprocess.check_output(['git','-C',str(back),'rev-parse','HEAD^{tree}'],text=True).strip(),resources=freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=cap),common_env={'TESY_CPU_WAVE_SKIP_PARKED':'1'},start_inventory={'schema':'c120-start-inventory-v1','duration_s':60,'max_age_s':3,'policy_sha256':sha256(d/'resource-policy.json')},capacity_projection_ESTIMATED=projection)
reference=root/'results/c127-slots40-numeric-20260929T1654Z/raw/c127-slots40-on01.capture';expected=json.loads((root/'results/c237-c75-rebuild-numeric-bridge-20261004/protocol.json').read_text())['reference_capture_tree'];assert tree_digest(reference)==expected
p['reference_capture_tree_revalidated']=expected
fixture=root/'results/c257-eagle3-multigrid-fidelity-20261004/development-native-inputs.json';gate=root/'tools/block_layer_reuse_gate.py';py=sys.executable
runs=[]
for label,mode in [('r0','r0'),('tile','r2-tile'),('reuse','r2-reuse')]:
 run_id='c262-'+label;out=d/'raw'/(run_id+'.capture')
 cmd=[str(build/'c262-c75-capture'),p['model_path'],str(root/'results/c2-target-numeric-v1.ids'),str(out),'--ngl','12'] if label=='r0' else [str(build/'block-layer-reuse'),p['model_path'],str(fixture),'anchor-nominal153',str(out),mode,'v1']
 post=[py,str(gate),str(out),'--output',str(d/(run_id+'-analysis.json'))]
 if label=='r0':post+=['--bridge-reference',str(reference)]
 else:post+=['--fixture',str(fixture),'--mode',mode]
 if label=='reuse':post+=['--paired-root',str(d/'raw/c262-tile.capture')]
 runs.append(dict(id=run_id,label=label+' selected numeric fresh process',variant='C75-private-'+mode,inventory=True,timeout_s=240,env={} if label=='r0' else {'TESY_C262_LAYER_SPAN':'153'},command=cmd,post_run_command=post,post_run_timeout_s=30))
p['runs']=runs
p['numeric_contract']={'R0':'Unchanged original ub32 topology without layer-span environment;189+32 bitwise originalC127 ON core/masks/logits;36 references reused only for equal original outputs/shapes/devices','R2':'Original target weights/router medium(ctx metadata)/ctx8192/fullSWA/F16/P12/slots40, attention/router span153 (new profile); native numericalFFN32/32/32/32/25, lastlayerout_ids one row; tile-major and expert-wave-major use same operators','selected':'All216 layer/stagepayloads, original canonical6component byte checks at CPU0/12/24 and GPU25/35, complete initial drained expert state,7fullfinite logits afterwarm153+six native published teacher-forced tokens','timing':'Capture not production timing; independent canonical new-shape references and causal/quality scopes remain required before promotion','gate':'No epsilon or relaxed shape; stop unit on any resource/identity/byte/read/lifetime/nonfinite/mismatch, retain partial raw; fixes require new identity'}
files=[d/'snapshot.json',d/'resource-policy.json',fixture,gate,root/'tools/test_block_layer_reuse_gate.py',root/'tools/block_layer_reuse_probe.cpp',root/'tools/block_native_run.cpp',root/'tools/c210_direct_reader.h',root/'tools/c210_witness_gate.py',root/'tools/residency_unit_run.py',root/'patches/c262-layer-expert-reuse.patch',build/'capture.cpp',build/'c262-c75-capture',build/'block-layer-reuse',root/'results/c2-target-numeric-v1.ids',back/'build-c262-cuda/CMakeCache.txt']
libs={}
for x in (build/'c262-c75-capture',build/'block-layer-reuse'):libs.update(backend_library_hashes(str(x),back))
assert any('cuda' in x for x in libs),libs
files+=[(Path(x) if Path(x).is_absolute() else back/x) for x in libs];files+=list(back/'src'/Path(x) for x in ['c262-expert-tiles.h','llama-graph.cpp','llama-context.cpp'])
p['file_sha256']={str(x.resolve()):sha256(x.resolve()) for x in files};p['binary_libraries']=libs
p['implementation_build']={'compiler':subprocess.check_output(['g++-15','--version'],text=True).splitlines()[0],'CUDA':'13.3/arch89','GGML_CUDA':True,'CPU_SKIP_PARKED_compile_flag':True,'backend_build':'build-c262-cuda','operational_C236':'unchanged, new backend owns copies and bridge required'}
assert not (d/'protocol.json').exists();(d/'protocol.json').write_text(json.dumps(p,indent=2,allow_nan=False)+'\n')
add=ep/'raw-roots-addendum.json';a=json.loads(add.read_text());a['effective_raw_roots'].append(str((d/'raw').relative_to(root)));a['reason']='Prospective append C262 private R0 bridge/R2 numeric only; all earlier raw preserved';add.write_text(json.dumps(a,indent=2)+'\n')
(d/'budget-admission.json').write_text(json.dumps(Epoch(ep).budget(1115,700*2**20),indent=2)+'\n')
assert json.loads((d/'budget-admission.json').read_text())['admitted']
print(json.dumps({'cap':cap,'estimate':projection,'runs':len(runs),'backend':p['backend_commit'],'libs':len(libs)},indent=2))
