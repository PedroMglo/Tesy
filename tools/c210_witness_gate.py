"""Prospective stronger C127 byte witness coverage; no historical reclassification."""
from collections import defaultdict
from pathlib import Path
import csv
from c2_gate import GateError
from c70_full_boundary_gate import inspect,_index,_values
FIELDS=['phase','layer','wave','logical','slot','generation','tensor','bytes','status']
SELECTED={('prefill0',0),('prefill0',25),('prefill0',29),('decode0',0),('decode0',25),('decode0',29),('decode0',35)}

def validate_rows(checks,expected):
 got={};groups=defaultdict(set)
 for row in checks:
  if set(row)!=set(FIELDS):raise GateError('witness fields invalid')
  try:
   phase=row['phase'];layer,wave,logical,slot,gen,tensor,size=[int(row[k]) for k in ('layer','wave','logical','slot','generation','tensor','bytes')]
  except (ValueError,TypeError):raise GateError('witness numeric metadata invalid')
  base=(phase,layer,wave,logical,slot)
  if (phase,layer) not in SELECTED or not 0<=logical<128 or not 0<=slot<40 or gen<=0 or not 0<=tensor<6 or row['status']!='EQUAL' or size!=(4406400 if tensor<3 else 11520):raise GateError('witness metadata/slice invalid')
  key=(*base,tensor)
  if key in got:raise GateError('duplicate witness component')
  got[key]=gen;groups[base].add(tensor)
 if set(groups)!=expected or any(v!=set(range(6)) for v in groups.values()):raise GateError('witness missing/extra consumption coverage')
 for base in groups:
  if len({got[(*base,k)] for k in range(6)})!=1:raise GateError('witness generation differs within consumption')
 return {'status':'PASS_PROSPECTIVE_WITNESS','combinations':len(groups),'components':len(got),'coverage':sorted(SELECTED)}

def witness(root):
 root=Path(root);indexed=_index(root);expected=set()
 for phase,layer in SELECTED:
  rows=[r for r in indexed if r['phase']==phase and int(r['layer'])==layer]
  routed=[r for r in rows if r['name']=='ffn_moe_topk']
  if len(routed)!=1:raise GateError('witness routing absent/duplicate')
  logical=_values(root,routed[0]);waves=[r for r in rows if r['name']=='ffn_moe_wave_ids'];masks=[r for r in rows if r['name']=='ffn_moe_wave_mask']
  if waves:
   if len(waves)!=len(masks):raise GateError('witness wave masks incomplete')
   for wave,(r,m) in enumerate(zip(waves,masks)):
    physical,mask=_values(root,r),_values(root,m)
    if len(physical)!=len(logical) or len(mask)!=len(logical):raise GateError('witness route lengths invalid')
    for expert,slot,active in zip(logical,physical,mask):
     if active==1:expected.add((phase,layer,wave,expert,slot))
  else:
   remap=[r for r in rows if r['name']=='ffn_moe_topk_stream']
   if len(remap)!=1:raise GateError('witness nonwave remap missing')
   slots=_values(root,remap[0])
   if len(slots)!=len(logical):raise GateError('witness remap length')
   expected.update((phase,layer,0,x,y) for x,y in zip(logical,slots))
 with (root/'byte_checks.tsv').open() as f:
  reader=csv.DictReader(f,delimiter='\t')
  if reader.fieldnames!=FIELDS:raise GateError('witness header changed')
  checks=list(reader)
 return validate_rows(checks,expected)

def qualified(root):
 out=inspect(root,skip_on=True);out['prospective_witness']=witness(root);return out
