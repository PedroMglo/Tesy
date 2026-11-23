# N2 runner boundary correction — preserve original model path

Date: 2026-09-23
Status: prospective implementation correction
Base before change: `686e204207353a0d71b06a5bc6d1d70a07cf3ff4`

## Finding

The stock smoke runner resolved the supplied model path with `realpath` before
calling Tesy's model verifier. The verifier correctly rejects symlinks, but a
pre-resolved path hides the fact that the user supplied a symlink.

The paired trace runner did not perform the full model/provenance preflight.

## Correction

Both model-bearing runners now verify the original path first. Only after a
PASS do they resolve the canonical regular-file path for execution.

The paired trace runner also records:
- live `tesy doctor` snapshot;
- Tesy HEAD and clean worktree status;
- pinned llama.cpp HEAD and clean worktree status;
- tracer SHA-256;
- locked model verification;
- trace summary;
- count-space LRU/Belady headroom.

A dirty worktree or backend-pin mismatch ends the campaign before model
execution.

## Claim boundary

This change hardens campaign provenance. It does not prove the physical host is
currently clean, does not open a model in this GitHub session and does not turn
routing counts into physical byte measurements.
