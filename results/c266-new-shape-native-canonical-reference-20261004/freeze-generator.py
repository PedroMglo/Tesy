import sys,json,subprocess,shutil
from pathlib import Path
sys.path.insert(0,'tools')
from host_resource_policy import freeze_protocol_resource_limits
from epoch_accounting import Epoch
from run_bounded import sha256
r=Path.cwd();old=r/'results/c265-native-probs-alias-repair-20261004';d=r/'results/c266-new-shape-native-canonical-reference-20261004';d.mkdir(exist_ok=False);ep=r/'results/c236-post-c235-blocks-expert-reuse-20261004T105527Z';p=json.loads((old/'protocol.json').read_text());policy=json.loads((old/'resource-policy.json').read_text())
assert json.loads((old/'numeric-summary.json').read_text())['status']=='PASS_R2_TILE_SHARED_FIDELITY'
for n in ['snapshot.json','resource-policy.json']:shutil.copyfile(old/n,d/n)
p.update(schema='c266-selected-native-canonical-r2-reference-v1',campaign_id='c266-new-shape-native-canonical-reference',execution_scope_unit='tesy-c266-native-canonical-reference',physical_envelope_s=540,raw_projection_bytes=8*2**20,success_status='PASS_SELECTED_NATIVE_CANONICAL_R2_REFERENCES',claim_scope='Three original native CPU/GPU FFN references on R2 captured inputs; full153 router and eleven native32/25/1 FFN tiles; not production timings',resources=freeze_protocol_resource_limits(policy,cgroup_memory_max_bytes=4*2**30))
p['runs']=[];exe=ep/'build/block-prefill-reference';capture=old/'raw/c265-tile.capture'
for layer,device in [(0,'cpu'),(25,'cuda'),(35,'cuda')]:p['runs'].append(dict(id=f'c266-layer{layer}',label=f'Canonical logical-expert independent layer{layer} {device}',variant=f'R2-native-canonical-{device}-{layer}',inventory=True,timeout_s=90,env={},command=[str(exe),p['model_path'],str(capture),str(layer),device]))
p.pop('repair',None);p['capacity_projection_ESTIMATED']={'storage_bytes':1697956352,'graph_meta_bytes':16*2**20,'workspace_and_uncertainty_bytes':2**30,'host_peak_projection_bytes':1697956352+16*2**20+2**30,'preventive_stop_bytes':4*2**30-512*2**20,'GPU':'Canonical logical pool128 ~1.70GB plus native graph workspace; GPU total guard7676MiB remains; previous target unloaded'}
p['numeric_contract']={'router':'Independent F32 native128×153 matmul+bias/topk/softmax (layer35 one row); full-span canonical validation before any FFN consumer','FFN':'Captured authoritative IDs/weights only after independent router PASS; original MXFP4 logical namespace128, same native device/32×4+25 or1, biases/SwiGLU1.702/7/down/weighted orderedtopk0..3; all eleven tiles bitwise and finite','bytes':'C211 fail-closed bounded O_DIRECT selected original slices only; exact GGUF encoding/range; canonical metadata<=64MiB','reuse':'C265 all216 R2tile/shared payloads and7logits bitwise; original36 C127references not repeated. New references cover changed153 router and FFN tail25; not fullattention8K/generalquality','gate':'Any router/weight/output/nonfinite/read/device/resource mismatch stops; no tolerance or silent shape32 inheritance'}
files=[d/'snapshot.json',d/'resource-policy.json',exe,r/'tools/block_prefill_reference.cpp',r/'tools/c7_layer_reference.cpp',r/'tools/c210_direct_reader.h',old/'numeric-summary.json',old/'raw-manifest.json',capture/'result.json']
for layer in (0,25,35):
 for stage in ('attn_post_norm','ffn_moe_logits','ffn_moe_logits_biased','ffn_moe_topk','ffn_moe_weights_softmax','ffn_moe_out'):files.append(capture/f'{stage}-{layer}.bin')
files+=[Path(k) for k in p['file_sha256'] if '/build-c262-cuda/' in k]
p['file_sha256']={str(x):sha256(x) for x in files};p['start_inventory']['policy_sha256']=sha256(d/'resource-policy.json')
(d/'protocol.json').write_text(json.dumps(p,indent=2,allow_nan=False)+'\n')
a=ep/'raw-roots-addendum.json';v=json.loads(a.read_text());v['effective_raw_roots'].append(str((d/'raw').relative_to(r)));v['reason']='C266 selected new native-shape references after C265 captured fidelity; preserve all observer failures';a.write_text(json.dumps(v,indent=2)+'\n')
b=Epoch(ep).budget(555,8*2**20);assert b['admitted'];(d/'budget-admission.json').write_text(json.dumps(b,indent=2)+'\n');print('C266 admission PASS')
