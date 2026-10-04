import sys,json,shutil
from pathlib import Path
sys.path.insert(0,'tools')
from epoch_accounting import Epoch
from run_bounded import sha256
r=Path.cwd();old=r/'results/c265-native-probs-alias-repair-20261004';d=r/'results/c267-layer-production-neutrality-20261004';ep=r/'results/c236-post-c235-blocks-expert-reuse-20261004T105527Z';p=json.loads((old/'protocol.json').read_text())
assert json.loads((d/'model-free-native-graph.json').read_text())['returncode']==0
for n in ['snapshot.json','resource-policy.json']:shutil.copyfile(old/n,d/n)
p.update(schema='c267-selected-layer-production-neutrality-v1',campaign_id='c267-layer-production-neutrality',execution_scope_unit='tesy-c267-layer-production-neutrality',physical_envelope_s=400,raw_projection_bytes=16*2**20,success_status='PASS_SELECTED_PRODUCTION_R2_INSTRUMENTATION_NEUTRALITY',claim_scope='Same R2 warm153 plus6teacher-forced calls, no tensor capture or canonical byte IO, seven full native logits bitwise captured profile; no latency claim')
run=p['runs'][1];run['id']='c267-clean';run['label']='R2 shared expert path capture/witness OFF, fresh same initial warmup';run['command'][0]=str(ep/'build/block-layer-reuse-c267');run['command'][4]=str(d/'raw/c267-clean.capture');run['command'][5]='r2-reuse-clean';run['post_run_timeout_s']=45
run['post_run_command']=[sys.executable,str(r/'tools/block_layer_reuse_gate.py'),str(d/'raw/c267-clean.capture'),'--fixture',run['command'][2],'--mode','r2-reuse-clean','--paired-root',str(old/'raw/c265-reuse.capture'),'--output',str(d/'neutrality-analysis.json')];p['runs']=[run]
p['file_sha256']={k:sha256(Path(k)) for k in p['file_sha256']}
for x in [d/'snapshot.json',d/'resource-policy.json',ep/'build/block-layer-reuse-c267',old/'numeric-summary.json',old/'raw/c265-reuse.capture/result.json',r/'results/c266-new-shape-native-canonical-reference-20261004/reference-summary.json']:p['file_sha256'][str(x)]=sha256(x)
p['start_inventory']['policy_sha256']=sha256(d/'resource-policy.json');p.pop('repair',None)
p['instrumentation_contract']={'disabled':'No observe stage/tensor request, no canonical reader/consumer witness. Same native numerical profile/libs/source and warmup/input IDs. Only selected full output logits persisted after each synchronized call','gate':'Explicit clean mode/falsecapture/zero capturebytes; seven nonempty finite full logits bitwise reference plus equal complete initial state; empty captures never pass the full-stage gate','next':'No production timing from this unit; benchmark must exclude output dumps, exact numerical plan and functional scopes remain declared'}
(d/'protocol.json').write_text(json.dumps(p,indent=2)+'\n');a=ep/'raw-roots-addendum.json';v=json.loads(a.read_text());v['effective_raw_roots'].append(str((d/'raw').relative_to(r)));v['reason']='C267 production observation neutrality after C265/C266 selected numeric/reference PASS';a.write_text(json.dumps(v,indent=2)+'\n');b=Epoch(ep).budget(415,16*2**20);assert b['admitted'];(d/'budget-admission.json').write_text(json.dumps(b,indent=2)+'\n');print('C267 admission PASS')
