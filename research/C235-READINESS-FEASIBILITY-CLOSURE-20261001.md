# C235 — minimal readiness overlap rejected in the tested scope

## Decision

`NO_GO_MINIMAL_READINESS_OVERLAP_IN_TESTED_SCOPE`.
Source audit, reused traces, three original native CPU operators and the
authorized isolated readiness pilot are complete. No Transformer was run,
no tokens generated, no shared C75 source/library or operational preset changed.
`FULL_FFN_RESTRUCTURE_ONLY_REMAINS_HYPOTHESIS` is a separate result, not GO
for implementation. The epoch closes now; no other flag/family is started.

## Authority and identities

Branch: `campaign/120b-post-c154-residency-20260930T094754Z`.
Base/origin observed: `425bda57dd1594037970a1d052e27fb22f602124`;
main `7a7d3dcbd1ff8e594ac57459c3db06306083c3ca`.
C231 closed LOCAL_ONLY then was published by the owner's prior authorization;
the new reconciliation preserves that history. This epoch is LOCAL_ONLY.

C233 measurement HEAD `dbd9586`; C234 measurement HEAD
`efcf4aa808008665f3e2c3fe07f6acc5cd517067`. Protocol/source/binary/private-object
and original mapped-library hashes are in the individual freezes/receipts.
The private pilot executable uses one original CPU C object with a readiness
callback; it does not replace the shared C75 runtime. C75 remains clean at
`27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5`, streaming base1248fd8….
Original model SHA/stat preserved without rehashing/scanning all weights.

Git signing via the configured SSH key failed (agent refused operation).
Subsequent local commits use a per-command unsigned override; signing settings
were not changed. No push/PR/merge/main/service/default changes were performed.

## Source and correctness — SOURCE_AUDITED / REPRODUZIDO_MODEL_FREE

Native execution is gate MMID→up MMID→SWIGLU→down→ordered reduction.
MMID scans physical slots ascending. Collective demand readiness precedes
the first projection in the existing remap; native workers publish RESIDENT
under the mutex after all three component tensor_set calls. Reserving/remapping
earlier and checking each expert/slot/generation before consumption can overlap
the first projection, but cannot turn this graph into complete per-expert FFNs.
Existing next-wave prefetch and passive waiting are separate mechanisms.

The pilot preserves the original dot/quantization/chunk and reduction code.
Immutable tags, native mutex/CV, release/acquire publication and keep pins
protect consumption. No slot reservation or eviction occurs while its graph
is live. Source restoration proves exactly one callback plus its declaration;
known-small F32 native controls produced independently expected dots and 64
callbacks with eight threads. Stale identity, pin loss before publication,
read error, cancellation and late worker tests passed without weights.
Six envelope tests and five analysis counterproofs passed; no full-suite claim.
Premodel compile/generator failures remain documented and raw errors retained.

## Operator measurement — MEDIDO_NO_TARGET, not server performance

C233 measured original CPU layers0/12/24 and C127 decode0/1/7/31, pool40/44
metadata, resident-hot and selected direct reload conditions. All288 records
are retained. Full FFN and first projection passed bitwise against the C127
reference chain. No36-reference rerun or full8K claim.
First projection medians are roughly0.27–0.30ms; full FFN medians0.88–0.93ms.
The outliers, including full FFN9.668734ms, remain in the published range.

Trace scopes stay separate:

| Origin | Decode denominator | Coarse first-op max scenario | First-op median scenario | Full-FFN median / max scenarios |
|---|---:|---:|---:|---:|
| C135 slots40 server, trace-on | 11.021767s / 46 evaluations | 4.792801% | not release-qualified | separate commit uncertainty |
| C163 slots44 C-API, trace-on | 11.281004s / 47 teacher-forced | 5.308648% | 1.558256% | 4.731906% / 9.787675% |
| C164 SQL slots44 C-API | 11.188811s | 5.843716% | 1.757799% | 5.215376% / 10.836665% |
| C164 energy slots44 C-API | 13.087705s | 5.625402% | 1.696382% | 5.021190% / 10.547136% |

These are **ESTIMADO / TEMPORAL_BOUND_CONDITIONAL**: fixed observed commits,
isolated timing range, capped by exposed service and the gross next-router gap.
That gap includes unshiftable attention/router work. C135 has transfer-return
intervals, not precise commit. Wake tail is separate and never double-counted.
Uniform-service/release and ascending-slot scenarios are explicitly conditional,
not a rigorous physical bound or production speedup. The optimistic slots44
range justified one bounded native pilot; it did not predict its outcome.

## C234 pilot — all outputs correct, benefit gate fails

Original native four-worker O_DIRECT loader and eight-thread CPU arithmetic,
one layer at a time. All-hit/mixed/all-absent are structurally selected trace
patterns from C163 calls11/12/19, applied to C127 captured decode0 IDs/activations.
This transfer does not recreate the original C163 expert IDs/working set.
Native component registration offsets match its snapshot. Initial loading and
neutrality FFN are declared; then each case runs eight repetitions ABBAABBA.
Timing includes reserve/enqueue, readiness/coordination and the original FFN;
canonical readback/witness is outside timing but inside physical charge.

All24 timed FFNs and the three initial FFNs were bitwise/finite against C127.
Each candidate exercised96 native consumer checks. Original selected component
bytes passed the direct witness. No missing expert, alternate router, changed
arithmetic, tensor callback/dump within timing or artificial delay was used
to obtain a timing benefit.

| Case | Four paired reductions, % | Median reduction | Median signed saving |
|---|---|---:|---:|
| all-hit | +5.0985, −45.8841, +8.3966, +35.8074 | +6.7476% | +81.8535µs |
| mixed | −6.7789, +1.7705, −28.8366, +24.6461 | −2.5042% | −278.8495µs |
| all-absent | −1.3313, +1.2673, −12.8058, +9.5441 | −0.0320% | −5.7005µs |

The favorable all-hit median does not establish a stable overhead guarantee;
its individual −45.88% pair fails the broad5% protection. No pair is removed.
Native loads/concurrent compute can change service times and scheduling;
these measurements do not isolate IO/cache/compute causes.

The frozen signed transfer charges negative case costs, gives all-hit positive
variance no readiness credit, and caps any positive overlap by wait/gap/first-op
work. Net full-decode scenarios: C163 **−1.382371%**, SQL **−1.513285%**,
energy **−1.451520%**. None sustains the required≥5% opportunity.
These are scenario arithmetic, not measured120B slowdowns. The observed
negative/unstable selected pilot and failed economic gate close this minimal
implementation; they do not prove a universal impossibility of readiness overlap.

## Resources, evidence and cleanup

2GiB STREAMING scopes, stop1.5GiB, swap0, own fresh60s inventories, live
device-derived guards. Maximum cgroup peaks across C233 layers:400326656,
411451392 and428982272B; C234:317427712B. No OOM/oom_kill/high/max/swap
events or guard/deadline/telemetry failures. C234 CPU47.625°C, GPU41°C,
NVMe32.85°C observed maxima; GPU total12MiB was unchanged background use.

Some C233 samples observe a buffered model descriptor during metadata-only
GGUF reading. SOURCE_AUDITED gguf.cpp:837–857 skips payload loading when
no_alloc=true. Payload/witness paths are O_DIRECT; C234 observed two direct
model fds and no buffered fd. No assertion of exclusively attributed physical
NVMe traffic or file charge is made. Metadata, original mapped libraries and
raw files also contribute to resources. Repeated selected experts/controller
caches, short sampling windows and external load limit timing transfer.

All new raw manifests SHA/size revalidated (about0.367MiB raw); captures,
original model and ELF/builds remain local. Every attempted sample/failure is
preserved. Cleanup found both units inactive/dead/MainPID0, no own operator or
model process, no GPU compute process. No experimental server port was created.
Other processes/listeners and the ordinary service were preserved.

Measured live charge is about320.729s including discovery, fixtures, inventories,
operators and cleanup. Precise wall/live/raw values and retired balances are in
`results/c235-readiness-feasibility-closure-20261001/budget-final.json` and the
append-only epoch ledger. Wall outside observed live spans includes build,
analysis and waits; human-category partition is DESCONHECIDO, not fabricated.

## Remaining hypothesis and program state

Full-FFN opportunity remains an optimistic hypothesis. Its boundary crosses
gate/up/activation/down graph nodes and would require a different per-expert
execution unit, generation/pin lifetime proof and independent native reference
while preserving router experts, dot and reduction order. Engineering cost and
net benefit under contention are DESCONHECIDO. The minimal next observation is
whether complete per-expert work can run before the last required release
without changing native arithmetic and without consuming the overlap in
coordination; the existing gross gap is insufficient. No larger scheduler,
fusion implementation or new physical family is authorized by this result.

DECODE: selected minimal per-slot readiness did not sustain a material net gain.
PREFILL/FIRST-FINAL: no new server/prefill/useful-latency evidence in this epoch;
this decode-only operator result does not predict those phases.

Slots40/ub32/GOMPunset remains the original C143/C188 opt-in, not default,
SESSION_PROFILE_IMPROVED_M4_NOT_MET; M3 PARTIAL. Slots44 retains C140/C142
and C203 original experimental scopes, not new qualification. C13319/20,
C164 rejected CPU52/GPU44, C206/C209/C222/C227 and all FAIL/NOT_RUN remain.
Native64, passive wait, mmap and tuning lines are not reopened. M4 NOT_MET.

Next action: review this local checkpoint and the explicitly limited full-FFN
hypothesis; no automatic epoch, runtime intervention or publication.
