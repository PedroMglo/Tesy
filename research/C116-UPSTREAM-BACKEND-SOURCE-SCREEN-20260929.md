# C116 — upstream source screen

Objective: test whether current upstream llama.cpp offers a bounded GPT-OSS 120B expert-residency path that justifies immediate build and model canary ahead of the warm153 decode investigation.

Base: Tesy `094751711693633bb06310496de60d10d07efd9a`; upstream `ggml-org/llama.cpp@8019dc563b1ecbae6b161a70c3a1359f1b206c1e`, clean shallow checkout in `/tmp/tesy-upstream-screen-20260929`. This is `SOURCE_AUDITED`, not target execution. The first static checker invocation failed because its source-line selector missed whitespace in the UP expert declaration; the selector was fixed before producing the result. No model was loaded.

The upstream source registers GPT-OSS, identifies 36 layers as 120B, implements its MoE graph with router-selected experts, and includes CUDA Ampere MXFP4 kernel configurations. The loader exposes mmap, DirectIO and a separate lazy row-reading mode. The explicit lazy mode applies only to tensors marked `TENSOR_READ_LAZY`. All three GPT-OSS expert weight declarations have flag `0`; this path does not supply explicit per-expert lazy residency for this model at this pin. Ordinary mmap can still fault file pages on demand, so these source facts do not prove the model cannot run under RAM pressure. They also give no target memory bound, numeric fidelity or performance result.

Decision: `BACKEND_SCREEN_NO_IMMEDIATE_BUILD`. A bounded loader/forward canary of this upstream pin would be a distinct numerical profile and needs a fresh capacity plan and time; it is lower priority than a phase-marked warm153 trace of the currently measured candidate. No weight download, build, physical run or service change. The source checkout remains outside Git.

Evidence: `results/c116-upstream-source-screen-20260929T1052Z/source-screen.json`, including source-file SHA256 and eight structural checks. Reproduce with `PYTHONDONTWRITEBYTECODE=1 python3 tools/c116_upstream_source_screen.py --source /tmp/tesy-upstream-screen-20260929 --output NEW_FILE.json` (output must not exist).

Alternatives: upstream mmap/page-cache execution may be viable; a future canary would have to verify live memory, exact GGUF, template/KV/SWA, mapped libraries, routing/FFN/logits and performance. No general backend NO_GO is claimed. C100 `NO_GO_CONFIRM` and all earlier FAILs remain unchanged. M3 retains C52b scope; M4 remains NOT_DEMONSTRATED.
