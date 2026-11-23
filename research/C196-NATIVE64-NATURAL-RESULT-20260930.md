# C196 — Native64 natural screen result

Measurement HEAD c8767c81d036719d8a8c41abd5e840d07b117bda; base C195 85aedb7eff1ec901debeb5628cc2fb79a54161ef. Four fresh processes, no recovery/retry. **NO_GO_S_SCREEN**, not numeric/resource/harness failure. All twelve requests natural and functional, all four arms exact nominal153, identity/resources/deadline gates PASS. C191/C192 scope preserved.

| Arm | T2 first-final s | SQL validated s | cold prefill s | warm prefill s | T2 completion s | T3 first-final s | nominal153 |
|---|---:|---:|---:|---:|---:|---:|---|
| c196-1-A32 | 18.402582 | 77.104809 | 62.724359 | 10.916644 | 18.722066 | 61.687033 | PASS |
| c196-2-B64 | 17.416675 | 97.392719 | 56.771291 | 9.843472 | 17.806210 | 80.369767 | PASS |
| c196-3-B64 | 18.120661 | 84.984809 | 56.784943 | 10.364158 | 18.509726 | 69.270666 | PASS |
| c196-4-A32 | 18.590910 | 77.457988 | 64.519366 | 11.122509 | 18.904000 | 62.094430 | PASS |

| Metric | Pair1 gain % | Pair2 gain % | Median % | Frozen gate |
|---|---:|---:|---:|---|
| T2_first_final_s | 5.357438 | 2.529461 | 3.943449 | >=15 and both positive |
| SQL_validated_s | -26.312120 | -9.717295 | -18.014708 | >=0 |
| cold_prefill_s | 9.490839 | 11.987754 | 10.739297 | >=-5 |
| cold_first_final_s | 6.992565 | 8.992803 | 7.992684 | >=-5 |
| T2_completion_s | 4.891849 | 2.085667 | 3.488758 | >=-5 |
| T3_first_final_s | -30.286323 | -11.556971 | -20.921647 | >=-5 |
| incremental_prefill_s | 9.830604 | 6.818165 | 8.324384 | >=-5 |
| decode_seconds_per_reported_output | -1.987973 | -4.677821 | -3.332897 | >=-5 |

## Decision and scope

T2 first-final gain3.943449% misses15%; SQL validated -18.014708% misses0%; T3 first-final -20.921647% violates -5% protection. This closes native64 natural investment **in this workload/profile scope**. Confirmation C197 NOT_RUN_S_GATE, with six unexecuted arms explicitly preserved. No threshold, output, date, prompt or grader changed.

Cold prefill gain10.739297%, incremental prefill8.324384% and cold first-final7.992684% are measured partial improvements. They do not compensate for primary/SQL/protection failure. Natural T2 seconds per reported output regressed3.332897% (within5% protection). W fixed-forward gain3.347632% remains a different workload.

Actual history and complete outputs/reasoning retained in local raw; request-summary has reported counts, input accounting, final content, stream clocks and validation. T1 reported counts A1/B2/B3/A4=77/78/78/77; T2 all37; SQL counts are in the request-summary (different natural output work). Do not claim equal compute. More/different reasoning is part of observed natural utility, not evidence of numerical corruption; no isolated causal attribution to arithmetic, temperature, cache or routing.

First-final already includes preceding prefill/reasoning; never add phase medians or first-final+prefill. No output ID retokenization; NOT_EXPOSED. File charge/faults/read_bytes are not physical NVMe traffic. No tensor observer/capture in timing.

All scopes had E18 cap/high and zero swap, per-arm60s inventory and strict internal Popen freshness. Runtime samples/provenance/cleanup and mapped-library hashes are in raw receipts and revalidated by original analyze_arm. Optional unavailable counters stay UNKNOWN. No usual service/default or power changes.

Baseline C75/P12/slots40/ub32 remains C188-validated opt-in, M3 PARTIAL, not default. Slots44 retains only prior C140/C142 scope. Native64 retains N/W limited scope; native64 natural utility not qualified. M4 NOT_MET. No full8K/session/quality12/holdout8/cold512/prefix4096 claims.

Next decision: retain ub32 opt-in; do not repeat this native64 screen or expand ubatch/slots automatically. A genuinely new workload/phase discriminant requires separate authority and frozen useful-latency hypothesis, not another attempt at this gate.

Evidence: results/c196-native64-natural-screen-20260930T223734Z; epoch results/post-c195-epoch-20260930T223734Z. 15 directed model-free methods PASS, not full repo suite. Raw/model/binaries remain local. Publication LOCAL_ONLY.

## Resource envelope and output differences

| Arm | Complete envelope s | cgroup peak B | GPU used MiB | CPU max °C | GPU max °C | NVMe max °C |
|---|---:|---:|---:|---:|---:|---:|
| A32 first | 245.994303 | 15770214400 | 6866 | 94.875 | 61 | 53.85 |
| B64 first | 257.778673 | 15750144000 | 6874 | 95.125 | 62 | 55.85 |
| B64 second | 246.123998 | 15742156800 | 6874 | 95.125 | 62 | 56.85 |
| A32 last | 247.033255 | 15728795648 | 6866 | 95.000 | 61 | 55.85 |

Zero workload swap/OOM/resource stops. CPU95.125 is warning-range data, not hardware FAIL. No pair excluded. Each arm fresh KV/pools, no cross-process state transfer; ambient/page cache/cooling state is operational context, not perfectly equalized. CPU clocks/package power not captured in this protocol, UNKNOWN; GPU power sampled.

Final answers matched across each A/B pair for T1/T2/SQL. T1 reasoning differs (77 A/78 B reported outputs), T2 reasoning matches (37 each), SQL reasoning differs (255 A/276 B). Input IDs and actual final histories match in this fixture, but this does not establish identical internal routing or compute across ubatch profiles. Full response/marker/sample paths and hashes are in request/resource summaries and raw-manifest.

## Reproduce the prospective decision from preserved rows

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 - <<'PY'
from pathlib import Path
from native64_numeric import read
from native64_evaluate import evaluate
r=Path('results/c196-native64-natural-screen-20260930T223734Z')
p=read(r/'protocol.json')
rows=[read(r/(rid+'-receipt.json'))['row'] for rid,_ in p['order']]
print(evaluate([(rows[0],rows[1]),(rows[3],rows[2])],'S'))
PY
```

Full offline arm revalidation uses `native64_natural.analyze_arm(root, run_id, profile, protocol, config)` and exactly reproduced each original row after process termination. Raw manifests are SHA256/size verified; no reinference needed. There is no accepted performance claim from invalid or incomplete evidence.
