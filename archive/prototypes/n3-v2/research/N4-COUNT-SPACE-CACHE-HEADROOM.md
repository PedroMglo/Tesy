# N4 count-space cache headroom gate

Date: 2026-09-23
Status: IMPLEMENTED / REAL_TRACE_NOT_RUN

## Purpose

Before implementing a native expert cache, use the exact routed expert-ID trace
to ask whether a bounded cache has any useful locality to exploit.

The analysis deliberately begins in count-space because exact per-expert encoded
byte spans have not yet been derived from the admitted GGUF.

## Policies

For each selected slot capacity Tesy reports:

- no-cache demand loads;
- causal LRU loads/hits;
- **Belady offline oracle** loads/hits;
- the infinite-cache compulsory-load lower bound.

Belady is exact for an equal-sized-object cache and uses future accesses. It is
therefore not implementable online; it is a lower bound on loads for the same
slot capacity.

This distinction is critical:

- LRU bad + Belady good => policy headroom exists;
- LRU ~= Belady and both good => simple locality may be enough;
- LRU ~= Belady and both bad => sophisticated prediction is unlikely to rescue
  that capacity in count-space;
- none of these conclusions establish byte or latency benefit until expert
  sizes and physical movement are measured.

## Command

After a paired exact trace passes:

```bash
tesy trace headroom-native routing.jsonl --slots 0,16,32,64,128,256
```

Use `--min-graph-seq` only when the campaign manifest prospectively defines
which graph sequences correspond to decode. Do not choose the cutoff after
looking at cache results.

## Stop rule

Do not implement a custom expert-cache mechanism merely because LRU has misses.

If the offline oracle shows negligible load reduction at all capacities that
are actually affordable on the reference host, record a negative N4 result and
pivot away from cache-policy complexity.

## Claim boundary

This analysis treats each (layer, expert) as one equal-sized slot. It is
TRACE_DERIVED_COUNT_SPACE. It does not measure NVMe bytes, page-cache activity,
DRAM traffic, PCIe transfers, kernel time, or end-to-end speed.
