# Native GGUF expert inventory result

Date: 2026-09-24  
Campaign: `results/native-expert-inventory-20260924T085418Z`  
Classification: `INCONCLUSIVE_EXECUTION_PROVENANCE_NOT_PRESERVED`

## Result

The metadata-only native GGUF inventory historically produced `PASS_DERIVATION`, but the committed publication does **not** preserve a reference-host identity/virtualization gate or the exact Tesy execution commit/tree. The host is therefore not proven physical and this publication is not admitted as reference-host evidence.

Measured/derived inventory:

- MoE layers: 24;
- experts per layer: 32;
- encoded payload bytes per expert: 13,253,760;
- merged expert tensor types: `f32`, `mxfp4`;
- merged expert tensor shapes:
  - `[2880, 32]`;
  - `[2880, 2880, 32]`;
- raw native tensor JSONL SHA-256:
  `58bb50aa1dcc9e5b3021e6908fa959f0dc264e50448f90ca93d31a28b91616f2`.

The native helper was built from the pinned llama.cpp/ggml source and reads
GGUF metadata with `no_alloc=true`. It does not use `gguf-py` or its
transitive Python dependencies.

## Source-backed structural interpretation

Pinned `src/models/openai-moe.cpp` defines for each gpt-oss MoE layer:

- gate/up/down expert weights shaped `[2880, 2880, 32]`;
- gate/up/down expert biases shaped `[2880, 32]`.

The historical observed type/shape set is consistent with three MXFP4 expert
matrices plus three F32 bias vectors per expert.

For MXFP4 at the pinned ggml layout, one 2880x2880 matrix slice is
4,406,400 encoded bytes. Three such matrices plus three 2880-element F32
biases yield exactly 13,253,760 encoded bytes per expert.

This interpretation is source-backed and arithmetic-derived; it is not a
physical fetch-granularity or transfer claim.

## Evidentiary correction

The encoded type/shape arithmetic remains useful descriptive metadata, but the campaign-level PASS is not reproducible from the committed evidence. A new inventory campaign must retain exact Tesy commit/tree and explicit reference-host verification before promotion.

The earlier 16 GiB/4 GiB byte-weighted simulation is also **not** promoted by this inventory result; it requires a new replay identity against the relocked inventory.

## Next gate

The native inventory blocker remains **open** for campaign admission. Before
the CPU-vs-transfer-vs-GPU expert crossover can be re-promoted, rerun the
inventory under a new campaign identity with exact Tesy commit/tree and
explicit `virtualization=PHYSICAL` evidence. The historical shape/type values
may guide implementation only; they are not admission authority.

The crossover must measure separately:

1. CPU-resident expert path;
2. requested Host->GPU weight transfer;
3. resident-GPU expert compute.

For the CPU-resident path, activation movement between GPU and Host must be
measured separately from CPU compute.

Requested copy bytes are not physical PCIe traffic.

## Claim boundary

Encoded GGUF payload bytes are not physical NVMe reads, DRAM traffic, PCIe
traffic, resident RAM or runtime allocation footprint.
