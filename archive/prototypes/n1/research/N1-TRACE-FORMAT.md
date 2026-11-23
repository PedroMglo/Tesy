# N1 normalized MoE routing trace

Status: DEVELOPMENT_ONLY schema for trace replay

Each JSONL line represents one routed MoE layer for one token:

```json
{"token": 17, "layer": 4, "phase": "decode", "experts": [{"id": 3, "bytes": 1048576}, {"id": 9, "bytes": 1048576}]}
```

Rules:
- `token` and `layer` are non-negative integers;
- `phase` is `prefill` or `decode`;
- `experts` is non-empty;
- expert IDs are unique inside one event;
- `bytes` is the encoded weight footprint assigned to that (layer, expert) object;
- the same (layer, expert) must keep the same byte size in one trace;
- events are ordered by token then layer;
- experts with the same ID in different layers are different cache objects.

This normalized format intentionally stores no prompt text and no hidden activations.

## What bytes means

At N1, `bytes` is a model-inventory/encoded footprint used by the simulator. It is not a claim of:
- physical NVMe reads;
- DRAM controller traffic;
- PCIe bus traffic;
- decompressed scratch size.

Native tracing must later publish separate counters for the quantities it can actually observe.

## Window analysis

`tesy trace summarize TRACE --windows 1,2,4,8` computes the union of (layer, expert) objects across observed target-token windows.

This is useful for asking whether multi-token work has potential expert reuse.

It is **not speculative acceptance evidence** because the trace consists of already-observed target tokens. Future candidate branches may route differently.

## Privacy

Raw prompts are unnecessary for routing-cache simulation and should not be recorded by default. Campaign metadata can carry a corpus identifier/hash separately.
