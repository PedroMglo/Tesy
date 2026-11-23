# Routed-layer exactness result

Date: 2026-09-24

Protocol: `ROUTED-LAYER-EXACTNESS-PROTOCOL-20260924.md`.

Measurement commit: `e09fdf6c6c9260ee94e2ae6d2d82a68bbe200baf`.
Measurement tree: `6450fc136126aa0f06fd2dfd0043365c44960641`.
Campaign: `results/routed-layer-exactness-20260924T165550Z/`.

## Objective and evidence class

Run the correctness-only routed-layer gate using one real layer-0 decode event
from the stock llama.cpp router. The stock `ffn_moe_out-0` tensor is the
authority. Results are measured numerical-parity evidence for this one event;
they are not timing evidence.

## Repairs before measurement

The frozen candidate commit failed its own lexical contract because its
claim-boundary prose used forbidden policy words. A successor only changed the
prose. The first native build then exposed a pinned-llama API mismatch: the
capture program passed a const token address to `llama_batch_get_one`, which
requires a mutable pointer. A successor made that local token mutable. Neither
repair changed routing, inputs, capture, weights, comparator, thresholds or
campaign policy. Their full record is
`ROUTED-LAYER-EXACTNESS-CONTRACT-REPAIR-20260924.md`.

## Gates and provenance

- Focused model-free: shell syntax, Ruff, compileall and 48 tests PASS.
- Full model-free: Ruff, compileall, shell syntax and 219 tests PASS.
- Model SHA-256 `52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`;
  size 12,109,564,352 bytes.
- Prompt SHA-256 `431498aa6a73a4e817c5ef58ceabdac5b8336dd95e01a17903e75bc1d27d10c6`.
- llama.cpp `4e416ee7308dd6b581796f1a6241276cd5982691`, clean worktree.
- Physical reference host PASS and no competing GPU compute process.
- Native provenance PASS. Mixed executable SHA-256
  `4ef4fde422dd6c457374cbda76640e482fae483d9a8700021c621e9dcf9888a8`;
  capture executable SHA-256
  `2e2505ef4bebf6599d1c3ec14fc9a48a888d202869009de55acee86ba781d88d`.
- Resource gate PASS: 10/10 valid GPU samples, zero failed samples and zero
  process swap. No `failure.json` exists.

## Result

Stock callback OFF and ON generated identical greedy token IDs: `[2167, 1309]`.
The callback captured a 2,880-float activation and stock output, selected real
experts `[1, 13, 17, 21]`, and final routing weights from
`ffn_moe_weights_softmax-0`.

| GPU hits | Serial vs stock relative max | Async vs stock relative max | Cosine |
| ---: | ---: | ---: | ---: |
| 2 | 5.60445568e-08 | 5.60445568e-08 | 1.0 |
| 3 | 5.60445568e-08 | 5.60445568e-08 | 1.0 |

Serial-vs-stock, async-vs-stock and async-vs-serial all passed at h=2 and
h=3. The recorded decision is `ROUTED_LAYER_EXACTNESS_GO`.

## Decision, limitations and next gate

This result admits preparation of a separate, prospective routed-layer timing
protocol. That protocol must preserve the captured exact route and stock
authority, define serial/async timing methods, tail and median thresholds,
resource limits and stop conditions before any timing measurement.

This single-event result does not establish bitwise equality, exactness for
other layers, prompts or tokens, token-distribution preservation, full-model
latency/throughput, placement benefit, prefetch behavior, physical traffic or
bytes per committed token.
