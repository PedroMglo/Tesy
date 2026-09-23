# Implementation status

Branch baseline date: 2026-09-23

| Capability | Status | Evidence boundary |
|---|---|---|
| N0 prior-art screen | IMPLEMENTED | broad novelty NO-GO; not exhaustive patent/legal review |
| model lock + SHA/size verifier | IMPLEMENTED | gpt-oss-20b identity frozen; local file not yet observed |
| host doctor | IMPLEMENTED | physical host NOT_RUN here |
| capacity planner | IMPLEMENTED | static admission only |
| backend provenance probe | IMPLEMENTED | stock llama.cpp source/binary surface only |
| llama.cpp source pin | IMPLEMENTED | exact upstream commit frozen |
| KTransformers source pin | IMPLEMENTED | reference only |
| vLLM source pin/role | IMPLEMENTED | B4 comparator; not installed/admitted on laptop |
| normalized routing schema | IMPLEMENTED | strict JSONL parser |
| passive raw routing schema/parser | IMPLEMENTED | router IDs only |
| passive native llama.cpp tracer | SOURCE_IMPLEMENTED | CI build pending; real model NOT_RUN |
| speculative expert-union analysis | IMPLEMENTED | trace-derived, not acceptance |
| RAM/VRAM demand-LRU simulator with NVMe backing | IMPLEMENTED | simulated bytes only |
| Python tests | CI_PASSING_ON_ACTIVE_HEAD_PRE_DOC_UPDATE | Python 3.11/3.12/3.13 observed passing before this documentation commit |
| stock llama.cpp reference-host build | NOT_RUN_HOST_REQUIRED | physical reference laptop required |
| real gpt-oss-20b load | NOT_RUN_MODEL_REQUIRED | user-managed model download |
| Harmony conversational trace | NOT_IMPLEMENTED | raw diagnostic is not a quality/corpus path |
| expert tensor-byte inventory | NOT_IMPLEMENTED | next N1 task after raw trace boundary |
| native expert residency/cache | NOT_IMPLEMENTED | intentionally blocked on baseline/trace evidence |
| CPU/GPU expert crossover benchmark | NOT_IMPLEMENTED | physical host required |
| causal prefetch | NOT_IMPLEMENTED | only after trace headroom |
| speculative K=2 | NOT_IMPLEMENTED | only after K=1 baseline/exactness |
| joint K/residency scheduler | RESEARCH_HYPOTHESIS_WEAKENED_BY_PRIOR_ART | broad novelty rejected |
| optimized Tesy chat | NOT_IMPLEMENTED | stock baseline first |
| gpt-oss-120b execution | NOT_AUTHORIZED_BY_EVIDENCE | metadata-only |

No IMPLEMENTED label implies real-model speed, quality or exactness unless it explicitly says REAL_MODEL_VALIDATED.
