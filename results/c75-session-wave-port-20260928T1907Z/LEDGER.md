# C75 session backend port

- Source: isolated C35 worktree commit `27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5`; patch `research/patches/C75-session-wave-skip-port.patch`. C35 was not modified.
- Build: CUDA arch 89, GCC 15, `TESY_C47_CPU_SKIP_PARKED`; `llama-server` built model-free.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c75_model_free_gate.py`: PASS for MXFP4/F16/F32 broadcast and FFN controls with poisoned scratch.
- Full model, server correctness and timing: NOT_RUN. C48/C61/C66 FAILs unchanged.
- Next gate: independent C75 full boundary OFF/ON with a new measurement commit and resource preflight.
