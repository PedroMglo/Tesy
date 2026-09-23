# N3 amendment — validate native graph signatures

Date: 2026-09-23
Status: prospective diagnostic hardening

The llama.cpp eval callback does not expose an absolute decode-token index.
Tesy's native tracer derives `graph_seq` when the observed MoE layer sequence
resets.

That derivation must not be trusted solely because the tracer compiles.

Before any route trace is used for cache analysis, Tesy now requires every
one-token evaluation group in the diagnostic run to expose the same ordered
signature:

```text
(layer_id, n_expert_used)
```

A missing layer, extra layer or changed top-k width produces FAIL.

Command:

```bash
tesy trace validate-native routing.jsonl
```

The paired exactness runner executes this check automatically before the
headroom analysis.

This does not establish absolute token numbering or physical traffic. It is a
structural consistency check for the trace grouping heuristic.

The first paired tracer campaign is CPU-only by default
(`TESY_TRACE_NGL=0`) to validate instrumentation without risking a full-GPU
OOM on an 8 GiB device. A later representative routing campaign must freeze
the actual hybrid placement prospectively and revalidate trace OFF/ON under
that placement.
