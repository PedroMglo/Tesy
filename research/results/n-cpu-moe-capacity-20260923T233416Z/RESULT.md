# n-cpu-moe capacity-only diagnostic

Campaign: `n-cpu-moe-capacity-20260923T233416Z`

Classification: `SOURCE_BACKED_CAPACITY_GATE`.

Build provenance: `PASS`.

Frozen stock auto-fit argv: `-c 4096 -ngl 25 -ot blk\.12\.ffn_(gate|up|gate_up|down).*=CPU,blk\.13\.ffn_(up|down|gate_up|gate)_(ch|)exps=CPU,blk\.14\.ffn_(up|down|gate_up|gate)_(ch|)exps=CPU,blk\.15\.ffn_(up|down|gate_up|gate)_(ch|)exps=CPU,blk\.16\.ffn_(up|down|gate_up|gate)_(ch|)exps=CPU,blk\.17\.ffn_(up|down|gate_up|gate)_(ch|)exps=CPU,blk\.18\.ffn_(up|down|gate_up|gate)_(ch|)exps=CPU,blk\.19\.ffn_(up|down|gate_up|gate)_(ch|)exps=CPU,blk\.20\.ffn_(up|down|gate_up|gate)_(ch|)exps=CPU,blk\.21\.ffn_(up|down|gate_up|gate)_(ch|)exps=CPU,blk\.22\.ffn_(up|down|gate_up|gate)_(ch|)exps=CPU,blk\.23\.ffn_(up|down|gate_up|gate)_(ch|)exps=CPU,blk\.24\.ffn_(up|down|gate_up|gate)_(ch|)exps=CPU`.

Admitted manual N values: 12, 16, 20, 24.

Rejected manual N values: 0, 4, 8.

Performance gate: `PASS`.

This campaign stops before timed llama-server observations. No rejected point was deliberately loaded to induce OOM.

The estimates are source-backed memory projections, not measured peak VRAM/RAM or physical transfer traffic. No Tesy speedup, >RAM or novelty claim follows.
