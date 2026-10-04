import json,sys,subprocess,shutil
from pathlib import Path
sys.path.insert(0,'tools')
from run_bounded import sha256
from epoch_accounting import Epoch
r=Path.cwd();old=r/'results/c262-layer-executor-numeric-20261004';d=r/'results/c263-layer-observer-name-repair-20261004';ep=r/'results/c236-post-c235-blocks-expert-reuse-20261004T105527Z';p=json.loads((old/'protocol.json').read_text())
assert json.loads((d/'model-free-native-graph.json').read_text())['returncode']==0
for x in ['resource-policy.json','snapshot.json']:shutil.copyfile(old/x,d/x)
p.update(schema='c263-exact-consumer-observer-fidelity-v1',campaign_id='c263-layer-observer-name-repair',execution_scope_unit='tesy-c263-layer-observer-name-repair',physical_envelope_s=740,raw_projection_bytes=600*2**20,success_status='PASS_R2_SELECTED_TILE_SHARED_FIDELITY')
p['claim_scope']='Corrected exact native tensor-name observer; same R2 profile/inputs/libs/cap; all-layer same-profile bitwise fidelity and six teacher-forced decode; not latency/quality'
p['runs']=p['runs'][1:]
for run in p['runs']:
 run['id']=run['id'].replace('c262','c263');run['command'][0]=str(ep/'build/block-layer-reuse-c263');run['command'][4]=run['command'][4].replace(str(old),str(d)).replace('c262-','c263-')
 run['post_run_command']=[x.replace(str(old),str(d)).replace('c262-','c263-') for x in run['post_run_command']]
p['repair']={'preserved_failure':str(old/'classification.json'),'mechanical_cause':'Exact layer suffix/name required; generated (view)/(cont) aliases ignored before type/bytes consumers','model_free_counterproof':'Actual production graph + derived view/cont callback selection tested with native metadata, no weights/forwards','unchanged':'Backend/source/libs/shape/inputs/cap/gates; no numeric repair or thresholds changed','R0_reuse':'C262 R0 selected bitwise bridge PASS; same private backend/libs; no original36FFN repetition'}
p['file_sha256']={k:sha256(Path(k)) for k in p['file_sha256']}
for x in [d/'resource-policy.json',d/'snapshot.json',ep/'build/block-layer-reuse-c263',old/'c262-r0-analysis.json',old/'raw/c262-r0.json',old/'classification.json']:
 p['file_sha256'][str(x)]=sha256(x)
p['start_inventory']['policy_sha256']=sha256(d/'resource-policy.json')
(d/'protocol.json').write_text(json.dumps(p,indent=2,allow_nan=False)+'\n')
a=ep/'raw-roots-addendum.json';v=json.loads(a.read_text());v['effective_raw_roots'].append(str((d/'raw').relative_to(r)));v['reason']='C263 prospectively repairs exact tensor-name observer only; preserve C262 failed partials and old immutable binary';a.write_text(json.dumps(v,indent=2)+'\n')
b=Epoch(ep).budget(755,600*2**20);assert b['admitted'];(d/'budget-admission.json').write_text(json.dumps(b,indent=2)+'\n')
print('C263 prospective two-arm admission PASS',b['physical_remaining_s'])
