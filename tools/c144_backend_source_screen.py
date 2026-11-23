#!/usr/bin/env python3
"""Pinned source-only capability matrix, no build/model/download."""
import argparse,hashlib,json,subprocess
from pathlib import Path
PIN='8019dc563b1ecbae6b161a70c3a1359f1b206c1e'
FILES=('src/models/openai-moe.cpp','src/llama-model-loader.cpp','src/llama-model.cpp','common/arg.cpp','common/chat.cpp','tools/server/server-context.cpp','ggml/src/ggml-cpu/ggml-cpu.c','ggml/src/ggml-cpu/arch/x86/quants.c','ggml/src/ggml-cuda/mmq-config-ampere.cuh')
def screen(source):
    actual=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if actual!=PIN or subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True):raise RuntimeError('pinned clean source required')
    texts={f:(source/f).read_text() for f in FILES}
    claims={
      'GGUF_MXFP4_loader':('src/llama-model-loader.cpp','LLAMA_FTYPE_MOSTLY_MXFP4_MOE','SOURCE_AUDITED'),
      'GPT_OSS_authoritative_MoE_graph':('src/models/openai-moe.cpp','n_expert, n_expert_used','SOURCE_AUDITED'),
      'CPU_MXFP4_dot_dispatch':('ggml/src/ggml-cpu/ggml-cpu.c','ggml_vec_dot_mxfp4_q8_0','SOURCE_AUDITED; actual AMD dispatch/build NOT_RUN'),
      'CUDA_Ampere_MXFP4_configs':('ggml/src/ggml-cuda/mmq-config-ampere.cuh','MXFP4','SOURCE_AUDITED; build/physical NOT_RUN'),
      'medium_template_kwarg':('common/chat.cpp','caps_apply_reasoning_effort','SOURCE_AUDITED; exact rendered IDs NOT_RUN'),
      'SWA_full_flag':('common/arg.cpp','--swa-full','SOURCE_AUDITED; model/runtime memory NOT_RUN'),
      'KV_unified_flag':('common/arg.cpp','--kv-unified','SOURCE_AUDITED; F16 runtime NOT_RUN'),
      'F16_KV_type_selection':('common/arg.cpp','--cache-type-k','SOURCE_AUDITED; selected type/runtime NOT_RUN'),
      'prefix_reuse_server':('tools/server/server-context.cpp','slot.task->params.cache_prompt','SOURCE_AUDITED; same target reuse NOT_RUN'),
      'CPU_expert_override':('common/arg.cpp','--cpu-moe','SOURCE_AUDITED; alternative numeric placement, not Tesy P12 equivalence'),
      'no_repack_flag':('common/arg.cpp','--no-repack','SOURCE_AUDITED'),
      'mmap_virtual_weight_path':('src/llama-model-loader.cpp','ggml_backend_tensor_alloc(buf_mmap, cur, data)','SOURCE_AUDITED; bounded resident set/forward NOT_RUN'),
      'GPU_tensor_full_upload_path':('src/llama-model-loader.cpp','ggml_backend_tensor_set(cur, data, 0, n_size)','SOURCE_AUDITED; explicit per-expert GPU streaming not established'),
    }
    checks={}
    for key,(f,needle,state) in claims.items():
        lines=[i for i,line in enumerate(texts[f].splitlines(),1) if needle in line]
        if not lines:raise RuntimeError('source claim not found '+key)
        checks[key]={'authority':state,'path':f,'lines':lines,'primary_source':f'https://github.com/ggml-org/llama.cpp/blob/{PIN}/{f}#L{lines[0]}'}
    return {'schema':'c144-source-capability-v1','source_commit':PIN,'dirty':False,'files':{f:hashlib.sha256((source/f).read_bytes()).hexdigest() for f in FILES},'capabilities':checks,
       'decision':'CONDITIONAL_MMAP_CPU_EXPERT_CANARY_NEXT_EPOCH; NO_PHYSICAL_BACKEND_IN_THIS_ORDER',
       'limits':['No target build, forward, numeric/functional or performance run','GPT-OSS expert flags remain0, as audited C116; explicit lazy row loading not established','mmap is file paging, not anonymous swap; virtual59GiB is not resident59GiB','A CPU-MoE override changes placement/profile and cannot inherit bitwise P12/quality/latency','Server fixed-date template/token IDs and API contract need explicit qualification','8GiB/32GiB support and interactive speed NOT_DEMONSTRATED'],
       'future_discriminant':{'hypothesis':'mmap-backed CPU experts with GPU attention can remain within cap without copying all expert weights into GPU; useful bounded baseline not assumed faster',
          'before_model':['pin exact source/toolchain/binaries','original GGUF hash/template/official ID arrays','calculate persistent nonexpert+KV+workspace+file-page residency separately','no_mlock; disable repack; explicit CPU experts and fixed memory cap','prove no transform/quantization/download and validate timing/quality as distinct profile'],
          'unit_proposal_not_authorized_now':'fresh epoch, bounded load/short forward, explicit cgroup/swap0/PSI/I/O guards; may OOM or be slow; stop on evidence/resource error',
          'no_go_scope':'no demonstrated bounded CPU/GPU per-expert stream at this pin; not physical impossibility or blanket upstream rejection'}}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with a.output.open('x') as f:json.dump(screen(a.source),f,indent=2,sort_keys=True);f.write('\n')
