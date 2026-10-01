# C154 — post-C145 epoch closure

## Result and authority

**BUDGET_CLOSED_WITH_PRESERVED_NOT_RUN.** Owner-authorized epoch began at
2026-09-30T01:16:45.447828Z. Six-hour wall deadline was
2026-09-30T07:16:45.447828Z. On resumption at 08:59 UTC the deadline had already
passed. No subsequent model, inventory, new physical family or optimization was
started. Closure reconciliation does not reopen the epoch.

At the 09:09:24 UTC accounting checkpoint: wall elapsed **28351.676 s**;
deduplicated conservative live charge **502.261 s**; unused physical allowance
**10297.739 s**, unusable because wall governs. Raw scanner reports 29694324 B;
a broader manifest accounts for 30401178 B of new non-build evidence, including
compact reports and fixtures. Limits were 21600 s wall, 10800 s live, 4 GiB raw,
with 900 s final physical reserve. Previous C145 balances were not transferred.

Wall includes interruption/waiting. Its split into engineering, builds, analysis
and pauses is UNKNOWN; it is not measured model-active time. Journal-reconstructed
metadata units have UTC-to-monotonic ESTIMATED placement and conservative one
second before/after each unit. Existing envelope rows remain unchanged.

## B — pinned upstream mmap CPU-MoE

Source pin `8019dc563b1ecbae6b161a70c3a1359f1b206c1e`, only the loader-prefetch
patch, original MXFP4 GGUF, ctx8192, CPU-MoE, ngl12 non-expert mapping. New profile;
no equivalence claim to streaming P12. FILE_PAGING distinguishes reclaim from
OOM and retains hard H20/swap-zero/host/device guards. Legacy streaming behavior
is preserved. Real no-weight runner smoke C147b passed after the preserved C147
terminal-smaps race failure. Relevant policy/entrypoint tests are recorded in
C147/C147b, not represented as a full repository suite.

Failures remain visible:

| Unit | Finding | Scope |
|---|---|---|
| C149 | model-lock identity rejected before launch | FAIL_HARNESS_PREMODEL |
| C150 | observer expected CPU instead of native CPU_Mapped | FAIL_OBSERVER_IDENTITY |
| C151 capacity | ctx8192 and one short forward completed | MEDIDO_NO_TARGET, short scope |
| C151 boundary | 140 s timeout, monitor reported 141.32 s before termination | NUMERIC_NOT_QUALIFIED |

C151 boundary maximum cgroup peak was 20941840384 B, file charge 20153376768 B;
GPU total used peaked at 1244 MiB; swap zero, no observed OOM. Reclaim/high events
were accepted in the explicit FILE_PAGING class. The instrumented observer also
checks canonical expert bytes; its timeout is not an uninstrumented performance
benchmark or a universal physical NO_GO for upstream/mmap. Numerical repeat,
36 canonical references, prefix qualification, screen and confirmation are
**NOT_RUN**. Page-cache ownership/equal-memory remained unqualified because some
other process mappings could not be inspected; no global cache flush occurred.

## A — prepared logical snapshot, not qualified physical tracing

Isolated backend commit `fec73fabdba3b5f3a67bf8a1c984b0ed8916bf03` descends from
trace pin `ba058e62c33f6e1c6d8581c4685d9abb64542027`; C75 production is preserved.
Source patch/generator/inl, C/C++ macros, copied pinned GGML hashes, build identity,
and native fixtures are reviewable. Build succeeded. No shared installation or
original production binary was replaced. Runtime mapped-library verification of
this new backend remains NOT_RUN.

Prepared snapshot copies logical manager/slot/queue/worker/generation state under
the existing mutex and writes outside it. Routed IDs include multiplicity and
publication sequence; RESIDENT_COMMIT is distinct from transfer return; explicit
BARRIER_SLOT events identify actual demanded generations, not next-wave preload.
Native tiny fixtures exercise remap hotness/decay/recency, pending work, duplicate
queue generations and wave behavior. Five codec/fixture tests pass; a closure
integrity rerun is saved, without loading weights.

**Remaining gates:** final generator byte-exact recheck after barrier additions;
journal unknown-kind/containment/bijection/commit negatives and legal asynchronous
cross-call control; same-binary boundary states/full-logit equality; physical
snapshot capture and phase overhead; faithful per-call/final-state replay,
independent heldouts and certified oracle. The new journal validator is draft
code, syntax checked but not declared ready. No retention or quota intervention
was selected or measured. No prediction of gain follows from these fixtures.

C153 has official vocab-only fixtures for development plus SQL and energy
heldouts. Full heldout transcripts have 2197 IDs, intended split 2044+153.
Development continuation reconstructed from C142 has 47 official IDs. The probe
plans 47 teacher-forced forwards; historical 47 output tokens involved 46 decode
calls, so these are different schedules. Its C API warm state is not claimed to
be C142's server state. Transcript payloads remain local with hashes; no private
prompt/raw or build was added to Git. No physical C153 capture was initiated or
frozen as a measured experiment.

## Preserved useful profiles and next decision

- Slots40 C75 remains opt-in `SESSION_PROFILE_IMPROVED_M4_NOT_MET`, M3 partial.
  C143 integration with weights remains NOT_RUN.
- Slots44 preserves C140 numerical/C142 nominal153 timing coverage. Broad
  quality/session/7936 coverage is not inherited.
- C35 remains explicit control. C100/C117/C122/C133 and all earlier failures
  retain their existing authority. **M4 NOT_MET; default/service unchanged.**

A new owner-authorized epoch is needed before physical continuation. First finish
the C152 journal controls and generation proof, then qualify same-binary numeric
and phase-overhead neutrality and capture development plus two independent
heldouts. Only a faithful replay and an applicable bound can select the single
static intervention; CPU48/quotas are not automatic next physical runs.

## Evidence and publication

Compact decision, final budget, append-only ledger, raw/fixture hash manifest,
C140/C142 integrity revalidation and model-free integrity log are under
`results/c154-post-c145-budget-closure-20260930T0900Z`. Both historical raw
manifests revalidated without inference. New raw and builds remain local.

Physical closure check: no own experimental process or c15* service active;
RTX4060 UUID unchanged, 12 MiB used, 43 C. Nothing was terminated outside this
epoch. Local commits only: no push, PR, merge, force-push, main/default change.
Per-command signing was disabled after earlier local GPG-agent refusal; global
Git signing configuration was not changed.
