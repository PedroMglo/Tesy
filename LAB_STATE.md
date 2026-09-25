# Tesy scale lab state

- Start: 2026-09-26 00:44 Europe/Lisbon (2026-09-25 23:44 UTC).
- Objective: exact routed inference of gpt-oss-120b above available RAM; primary target >=2 sustained decode tokens/s, then 4 and exploratory 8. Task benefit is a separate gate.
- Main state: IN_PROGRESS. Milestones demonstrated: none yet. Optimization interventions: 0/6. Four-hour active-work ceiling: 2026-09-26 04:44 Europe/Lisbon; actual session limit may be lower.
- Lab location: `/home/pmglo/Projects/Tesy/tesy-scale-lab`. Preferred sibling path was absent and outside writable roots. This is a separate nested Git repository on branch `scale-lab`; the pre-existing Tesy branch/worktree is untouched.
- Surrogate: local gpt-oss-20b MXFP4 GGUF, 12,109,564,352 bytes, SHA-256 `52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`, revision `a7443ebb00ba299cbbbf7e9b69487670447ae8c0`. No execution result yet.
- Target: local `openai/gpt-oss-120b` original MXFP4 safetensors, revision indicated by local Hugging Face tree `b5c939de8f754692c1647ca79fbf85e8c1e70f8a`; seven shards total 65,248,815,744 tensor bytes. GGUF target artifact is absent. No execution result yet. Full shard SHA-256 verification has not run.
- Backends: stock `ggml-org/llama.cpp` at `4b1a27fa0eb875bbca4f6cfe936e3d65adc685c0`; one streaming candidate `freedomljc/llama.cpp` at `1248fd8fa8cfebaece5ea992e4d951c1e18bb9d5`. The latter is a July 2026 snapshot and not established compatible with current stock.
- Last correct commit/configuration: none; compilation and correctness pending.
- Host: physical Fedora laptop indicators match Ryzen AI 9 HX 370, RTX 4060 Laptop 8188 MiB, 30 GiB reported RAM, NVMe `/dev/nvme0n1p3` btrfs `/home`. `MemAvailable` at inventory 24 GiB; zram swap 15 GiB, unused. Driver 615.71.09, CUDA toolkit 13.3.73. GPU temperature 45 C idle. Power limit unavailable. Cgroup v2 is mounted; current scope reports `memory.max=max`, `memory.swap.max=max`. Delegated limit has not been established.
- Current bottleneck: unknown. Source audit shows candidate streams GGUF expert weight tensors, not native safetensors. GGUF 120B compatibility remains untested.
- Next gate: finish builds, perform bounded 20B stock/candidate smoke with manifest/resource watchdog and then compare fixed-prefix numerics. Do not run the 120B from these safetensors with the GGUF-only candidate.

See `research/M0-M05-20260926.md` for evidence classes, budget and limitations.
