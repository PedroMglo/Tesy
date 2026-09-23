# N6 byte-weighted trace simulation

Date: 2026-09-23
Status: IMPLEMENTED / REAL_TRACE_AND_INVENTORY_NOT_RUN

## Purpose

After N3 produces exact routed expert IDs and N5 produces a PASS_DERIVATION GGUF expert inventory, Tesy can replay one-token decode routing with model-specific encoded expert payload sizes.

This closes the gap between equal-sized count-space slots and byte-aware cache planning without pretending to measure hardware traffic.

## Command

    tesy trace simulate-native results/routing.jsonl \
      --inventory results/gpt-oss-20b-expert-inventory.json \
      --ram-cache-gib 16 \
      --vram-cache-gib 4 \
      --min-graph-seq 1

The campaign must freeze min_graph_seq before looking at cache outcomes. It may not be selected post hoc to remove an inconvenient prefix.

## Policy being simulated

    selected expert
      -> hit VRAM: no modeled weight move
      -> miss VRAM / hit RAM: encoded expert bytes RAM->VRAM
      -> miss RAM: encoded expert bytes NVMe->RAM, then RAM->VRAM

Both RAM and VRAM use byte-capacity LRU.

This assumes GPU execution for every routed expert and therefore is not a simulation of --cpu-moe. It is a candidate-policy model used to quantify whether hot-expert residency could have enough byte headroom to justify native engineering.

## Interpretation

Report separately:
- simulated NVMe->RAM expert payload bytes/token;
- simulated RAM->VRAM expert payload bytes/token;
- RAM hit/miss/eviction counts;
- VRAM hit/miss/eviction counts.

Do not add the two tiers together and call the sum physical bytes.

## Stop rule

A custom GPU expert cache is not justified merely by a high LRU hit rate.

If byte-weighted benefit is small at capacities that leave realistic room for shared weights, KV, scratch and OS usage, preserve the negative result and test a different execution boundary such as CPU-resident expert compute.

## Claim boundary

Classification: TRACE_DERIVED_ENCODED_PAYLOAD_SIMULATION.

It is not measured storage I/O, page-cache traffic, memory-controller traffic, PCIe traffic, latency or throughput.
