# C233 native CPU operator; C234 readiness pilot freeze

## Authority and state

Post-C231 owner order, base `425bda57dd1594037970a1d052e27fb22f602124`.
C233 measurement HEAD `dbd9586`; original C75 shared libraries/source unchanged.
Local evidence only; no push, Transformer execution or generated tokens authorized.

## C233 — MEDIDO_NO_TARGET, isolated operator

Three CPU layers 0/12/24, captured C127 decode0/1/7/31 activations,
authoritative selected experts/slots/weights, native MXFP4 CPU arithmetic,
threads8. Original40/44 pool metadata, all 288 records retained. Full FFN
bitwise to original C127 ON; first gate projection bitwise to the same full
graph; canonical bytes verified with bounded O_DIRECT C211.

| Layer | Pool | First MMID min / median / max, µs | Full FFN min / median / max, µs |
|---|---|---|---|
| 0 | 40 | 186.571 / 268.155 / 797.971 | 643.851 / 884.811 / 1515.411 |
| 0 | 44 | 185.338 / 293.522 / 1025.490 | 661.184 / 918.569 / 9668.734 |
| 12 | 40 | 219.223 / 276.230 / 917.837 | 756.313 / 892.950 / 1595.192 |
| 12 | 44 | 184.257 / 290.156 / 776.250 | 626.208 / 927.270 / 1604.720 |
| 24 | 40 | 173.136 / 298.627 / 938.295 | 640.155 / 929.875 / 1676.274 |
| 24 | 44 | 202.521 / 268.169 / 738.710 | 656.505 / 879.019 / 1614.488 |

The 9668.734µs sample remains in the range, not censored as inconvenient.
Resident-hot and bounded selected-slice reload conditions are separately
available in raw; these isolated ranges are not universal production bounds.
The source and known-small native graph prove execution order gate→up→down,
although up is constructed first. MMID visits physical slots in ascending
order. No complete per-expert FFN runs ahead of another in this minimal plan.

## Offline scenarios — ESTIMADO / TEMPORAL_BOUND_CONDITIONAL

| Origin | Own decode denominator | Coarse first-op optimistic scenario |
|---|---|---|
| C135 slots40 server trace-on | 11.021767s, 46 evaluated calls | 4.792801% |
| C163 slots44 C-API trace-on | 11.281004s, 47 teacher-forced calls | 5.308648% |
| C164 SQL slots44 C-API | 11.188811s | 5.843716% |
| C164 energy slots44 C-API | 13.087705s | 5.625402% |

These use the maximum first projection observed per corresponding pool.
C135 has only transfer-return≤commit≤WAIT_END intervals, not measured commit.
C163/C164 use generation/expert/slot-matched RESIDENT_COMMIT. Service overlap
is capped by observed wait, isolated compute and the gross next-router gap.
Wake tail is separate; LOAD/WAIT/READ are never summed as independent costs.
Uniform per-expert releases and fixed slot order give lower conditional
scenarios (about 2.2–2.4% for the slots44 ordered example). First-op setup,
I/O/compute contention and transfer to the server remain unknown.

The separately capped **full-FFN** maximum scenarios are approximately
9.79–10.84%. They relax graph boundaries and include unshiftable work in the
gap, so they remain a hypothesis for a larger restructuring, not measured gain.

## C234 — prospective single isolated pilot

The optimistic first-op interval crosses 5% in an identified slots44 scope;
the source admits a consumer check without changing dot/reduction arithmetic.
Decision: `GO_ONE_BOUNDED_PILOT`, to resolve coordination/net-benefit uncertainty.

Original C75 loader/workers, O_DIRECT fds explicitly checked, original component
registration order from C163 snapshot. Only a private CPU C executor object
is compiled with the original flags plus one pre-consumer callback. No shared
runtime/backend is replaced. Its independent F32 known-small fixture passed
with 64 native callbacks, eight threads and native graph order.

All-hit/mixed/all-absent cases are the first structural matches in validated
C163: layer12 call11, layer24 call12, layer0 call19. Only positional miss masks
transfer to captured C127 decode0 activations/IDs. This is **not** a replay of
the original trace's routing or state. Four original I/O workers load the
same selected canonical slices in both arms. Initial load/neutrality FFN and
eight repetitions ABBAABBA per case are declared; repeated selected experts
and retained device caches limit transfer to cold/production workloads.

Immutable request tags and keep pins survive all consumers. Missing slots
wait under original mutex/CV for correct expert/slot/generation; release/acquire
publication follows native RESIDENT commit. No reserve/eviction while a graph
is live. Tests reject stale generation, wrong expert, lost pin before
publication, read error, cancellation, late worker after cancel and unknown
slot. Fast path assumes the proven pin/no-writer lifetime, not a rogue writer.

Freeze: `results/c234-readiness-pilot-or-bound-20261001/{protocol,cases,analysis-contract}.json`.
2GiB STREAMING scope, swap0, preventive stop1.5GiB, own 60s fresh inventory,
process deadline120s, family210s, external bound225s. Numerical mismatch,
reader/resource/evidence failure ends the unit; no physical retries.

GO for integration design requires all outputs bitwise/finite/witness PASS,
median paired all-hit regression≤5%, and signed net opportunity≥5% of full
decode under the explicitly frozen transfer scenario. Every sample is retained.
No production speedup, new opt-in, quality/M3/M4 or full-FFN implementation
can be concluded here. Slots40/ub32 remains the original opt-in.

## Failures, budget and next gate

Two model-free preparation errors (include-name assertion and a fixture main
macro conflict) were corrected before any pilot weights; build-error raw is
retained. Six directed envelope tests and both native model-free fixtures
passed; this is not the full repository suite.
C233 measured family charge192.283236s. At C234 admission the epoch has about
645s live remaining; next worst case225s fits with the 900s wall closure reserve.
Next authorized gate is this single C234 native pilot, then decision/closure.
