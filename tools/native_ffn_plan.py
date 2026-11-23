"""Strict native scheduling-plan evidence and immutable comparison; no numeric inference."""
import copy,json,re,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
NODE={'index','name','op','backend','output_buffer','dtype','shape','op_params','inputs','optimizer_dependencies'}
INPUT={'name','op','backend','storage_buffer','dtype'}
def keys(x,k):
 if type(x)!=dict or set(x)!=k:raise ValueError('plan fields differ')
def validate(raw):
 keys(raw,{'schema','no_alloc','variants'})
 if raw['schema']!='tesy-native-scheduled-plan-v1' or raw['no_alloc'] is not True:raise ValueError('not metadata-only plan')
 if [v['tokens'] for v in raw['variants']]!=[32,1]:raise ValueError('schedules')
 for v in raw['variants']:
  keys(v,{'tokens','scheduler_splits','nodes'})
  if type(v['scheduler_splits'])!=int or v['scheduler_splits']<=0:raise ValueError('splits')
  for i,n in enumerate(v['nodes']):
   keys(n,NODE)
   if n['index']!=i or n['backend'] not in ('CPU','CUDA0') or n['dtype'] not in ('f32','f16','i32','i64','mxfp4'):raise ValueError('node identity')
   if len(n['shape'])!=4 or any(type(d)!=int or d<=0 for d in n['shape']):raise ValueError('shape')
   if len(n['op_params'])!=16 or any(type(p)!=int for p in n['op_params']):raise ValueError('params')
   if not all(type(s)==str for s in n['optimizer_dependencies']):raise ValueError('deps')
   for x in n['inputs']:
    keys(x,INPUT)
    if x['backend'] not in ('CPU','CUDA0'):
     if x['backend']!='UNKNOWN' or x['op']!='NONE' or not x['name'].startswith(n['backend']+'#') or x['storage_buffer']!='UNALLOCATED':raise ValueError('input backend unknown outside scheduler copy')
 return raw

def compact(raw):
 validate(raw);out=[]
 for v in raw['variants']:
  for l in range(36):
   ns=v['nodes'];a=next(i for i,n in enumerate(ns) if n['name']==f'attn_post_norm-{l}');z=next(i for i,n in enumerate(ns) if n['name']==f'ffn_moe_out-{l}');ops=[]
   for n in ns[a:z+1]:
    op=copy.deepcopy(n);op['source_reference']=source(n);op['kernel_or_dispatch']=dispatch(n);op['accumulation']=arithmetic(n)
    op['copies']=[{'source':x['name'].split('#')[1],'target_backend':n['backend'],'evidence':'native scheduler-generated copy; public get_tensor_backend does not expose copy assignment'} for x in n['inputs'] if x['backend']=='UNKNOWN']
    ops.append(op)
   out.append({'layer':l,'tokens':v['tokens'],'ops':ops})
 return {'schema':'tesy-native-ffn-plan-v1','evidence':'SOURCE_AUDITED_NATIVE_METADATA_SCHEDULER','execution':'NO_WEIGHTS_NO_FORWARD','plan_layers':out}

def dispatch(n):
 if n['optimizer_dependencies'] and 'ffn_moe_out' in n['name']:return 'ggml_cuda_op_moe_weighted_reduction; matcher witness; memory-range guard at compute'
 if n['backend']=='CPU' and n['op']=='MUL_MAT_ID':return 'ggml_compute_forward_mul_mat_id; MXFP4/Q8_0 vec_dot; CPU dispatch'
 if n['backend']=='CPU':return 'ggml_compute_forward_'+n['op'].lower()
 return 'ggml_cuda_compute_forward / '+n['op']+'; callback graph boundary/fusion lifetime must match'

def arithmetic(n):
 if n['optimizer_dependencies'] and 'ffn_moe_out' in n['name']:return 'F32; expert order 0..3; fused multiply-add permitted (-use_fast_math); GPU scalar sequential sum'
 if n['op']=='MUL_MAT_ID':return 'MXFP4 weights; activation Q8_0 CPU dot; F32 outputs; pinned dispatch'
 return n['dtype']+' pinned backend operation; op_params/order preserved'

def source(n):
 return 'src/llama-graph.cpp:2002-2365; src/models/openai-moe.cpp; ggml/src/ggml-backend.cpp:1056-1550; '+('ggml/src/ggml-cpu/ggml-cpu.c' if n['backend']=='CPU' else 'ggml/src/ggml-cuda/ggml-cuda.cu:3032-3183,3443-3462; ggml/src/ggml-cuda/moe-weighted-reduction.cu')

def compare_plan(actual,expected):
 validate(actual);validate(expected)
 if actual!=expected:raise ValueError('native scheduling plan changed; requalification required')

def map_rows(raw):
 validate(raw);rows=[]
 for l in range(36):
  stages=[]
  for v in raw['variants']:
   d={n['name']:n for n in v['nodes']}
   s=[d[f'{x}-{l}']['backend'] for x in ('ffn_moe_logits','ffn_moe_gate','ffn_moe_out')]
   if d[f'ffn_moe_gate-{l}']['inputs'][0]['dtype']!='mxfp4' or s[1]!='CPU':raise ValueError('expert compute contract')
   fusion=bool(d[f'ffn_moe_out-{l}']['optimizer_dependencies'])
   if (s[2]=='CUDA0')!=fusion:raise ValueError('weighted reduction witness')
   stages.append((*s,int(fusion)))
  if stages[0]!=stages[1]:raise ValueError('shape-specific map; no shared reference map')
  rows.append((l,*stages[0]))
 return rows
