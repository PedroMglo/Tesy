# 120B evidence Git checkpoint — 2026-09-28

- Objective: preserve the compact evidence accumulated through C51 before starting a new physical unit.
- Base: `8e32e7ea16c7ee7b7f1c07d7b4e2a1b993cfde5c`, branch `campaign/120b-wave-critical-20260928-0814utc`; worktree clean before this checkpoint.
- Evidence class: Git tracking and local SHA audit, no model execution.
- Audit: [checkpoint index](../results/120b-git-evidence-checkpoint-20260928T1124Z.json) covers 58 indexed units. The 128 manifest-listed C40–C51 files checked matched their SHA256 values. C7, C7b, C8 and C15 predate `decision.json`; their existing compact protocol, result and checkpoint files are tracked. C41 stopped before model launch and has no manifest.
- Decision: compact evidence remains local in Git. The raw evidence remains local and referenced by manifests; raw traces, model weights, binaries, caches and private prompts are excluded by `AGENTS.md`.
- Alternatives: adding the raw directory to Git would copy large and potentially private traces; omitted under the repository contract.
- Tests: Git tracking and hashes above. New model, timing and sustained session: NOT_RUN at this checkpoint.
- Failures: the historical C47/C48/C50 and thermal failures retain their recorded statuses. The four legacy units without `decision.json` are an older output schema, not newly inferred failures.
- Limitation: this checkpoint does not reaudit every historical raw file or certify the historical numeric claims.
- Next gate: freeze and run a separately budgeted 20-request actual assistant-history session under the C51 profile, if current preflight and remaining physical budget admit it.
