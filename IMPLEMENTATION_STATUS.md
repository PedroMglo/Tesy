# Implementation status

Branch baseline date: 2026-09-23

| Capability | Status | Evidence boundary |
|---|---|---|
| N0 prior-art screen | IMPLEMENTED | research docs; not exhaustive legal/patent review |
| model lock + SHA verifier | IMPLEMENTED | source code; real download not verified in this session |
| host doctor | IMPLEMENTED | source code; physical host NOT_RUN here |
| capacity planner | IMPLEMENTED | static admission only |
| normalized routing schema | IMPLEMENTED | strict JSONL parser |
| speculative expert-union analysis | IMPLEMENTED | trace-derived, not acceptance |
| RAM/VRAM demand-LRU simulator with NVMe backing | IMPLEMENTED | simulated bytes only |
| unit tests | IMPLEMENTED_NOT_RUN | no repo shell in this GitHub-only session |
| stock llama.cpp build | NOT_RUN_HOST_REQUIRED | backend not pinned/built yet |
| real gpt-oss-20b load | NOT_RUN_MODEL_REQUIRED | user-managed model download |
| native routing trace capture | NOT_IMPLEMENTED | next backend task |
| native expert residency/cache | NOT_IMPLEMENTED | requires backend integration |
| CPU/GPU expert crossover benchmark | NOT_IMPLEMENTED | physical host required |
| causal prefetch | NOT_IMPLEMENTED | only after trace headroom |
| speculative K=2 | NOT_IMPLEMENTED | only after K=1 runtime/exactness |
| joint K/residency scheduler | RESEARCH_HYPOTHESIS | novelty and benefit not established |
| optimized Tesy chat | NOT_IMPLEMENTED | stock baseline first |
| gpt-oss-120b execution | NOT_AUTHORIZED_BY_EVIDENCE | metadata-only |

No line marked IMPLEMENTED implies real-model performance or correctness unless it explicitly says REAL_MODEL_VALIDATED.
