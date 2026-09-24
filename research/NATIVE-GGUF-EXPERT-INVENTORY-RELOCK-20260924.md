# Native GGUF expert inventory relock

Date: 2026-09-24  
Branch: `research/native-expert-inventory-20260924`  
Classification: prospective metadata-only gate

## Purpose

The earlier gpt-oss-20b expert inventory found 24 MoE layers, 32 experts per
layer and 13,253,760 encoded bytes per expert, but that result was not admitted
because the `gguf-py` transitive Python environment was not frozen
prospectively.

Do not solve that by pinning an unnecessary Python dependency tree.

The pinned llama.cpp GGUF C API already exposes the authoritative tensor table:

- tensor name;
- file-order dimensions;
- ggml type;
- encoded tensor size;
- tensor data offset.

This gate replaces `gguf-py` with a tiny Tesy helper linked against the
pinned llama.cpp/ggml implementation.

## Source semantics checked before implementation

At llama.cpp commit
`4e416ee7308dd6b581796f1a6241276cd5982691`:

- `gguf.cpp` reads tensor dimensions into `info.t.ne[j]` in file order;
- `gguf-py GGUFReader` exposes `ReaderTensor.shape = dims` in the same
  file order;
- therefore the existing Tesy rule using the final GGUF dimension as expert
  count is preserved without transpose/reverse ambiguity.

## Native helper boundary

`tesy-gguf-inventory`:

- uses `gguf_init_from_file(..., no_alloc=true)`;
- requests a metadata `ggml_context`;
- never allocates tensor payloads;
- never initializes CUDA;
- never executes a Transformer graph;
- emits one strict JSONL metadata record per GGUF tensor.

The helper does not implement a GGUF parser. Parsing, type/shape validation and
encoded size calculation remain llama.cpp/ggml responsibilities.

The separate build uses `GGML_CUDA=OFF` because this is a metadata gate.

## Derived inventory

`tesy.native_gguf_inventory` uses only the Python standard library plus Tesy
source.

It validates:

- exactly one header;
- exact tensor count;
- sequential tensor IDs;
- unique non-empty names;
- positive dimensions and encoded sizes;
- absolute offset = GGUF data offset + relative tensor offset.

Validated records are converted to the existing strict `TensorRecord` type
and passed to `derive_expert_payload_inventory`.

For merged `*_exps` tensors, the existing fail-closed rule remains:

`encoded_payload_bytes_per_expert = tensor.n_bytes / tensor.shape[-1]`

only when division is exact and all merged expert tensors in a layer agree on
the expert count.

## Provenance

The physical run must freeze/record:

- Tesy HEAD and clean worktree;
- llama.cpp exact pinned HEAD and clean worktree;
- locked model verification;
- native inventory binary SHA-256;
- dynamic library resolution;
- raw JSONL SHA-256 through the derived result.

No Python package-version claim is needed because the inventory path no longer
imports `gguf-py`, NumPy, tqdm, PyYAML or Requests.

## Operator gate

After focused model-free checks and a clean worktree:

```bash
campaign="results/native-expert-inventory-$(date -u +%Y%m%dT%H%M%SZ)"

bash scripts/run_native_expert_inventory.sh \
  /home/pmglo/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf \
  "$campaign"
```

Successful execution must print:

`PASS_NATIVE_GGUF_EXPERT_INVENTORY`

Do not hard-code the old exploratory counts/types/shapes as a PASS condition.
Compare them only after the new independently admitted result exists.

## Next gate

Only after this inventory passes on the reference host should Tesy freeze the
CPU-vs-transfer-vs-GPU expert crossover.

The crossover must use the newly admitted real shapes/types and measure
separately:

1. CPU-resident expert compute latency;
2. requested Host->GPU transfer latency and requested bytes;
3. already-resident GPU expert compute latency.

Requested transfer bytes are not physical PCIe traffic. A later physical-PCIe
claim requires a suitable hardware/driver counter.

Do not implement a Tesy cache, prefetch scheduler or custom MoE runtime merely
to perform this measurement. Reuse the smallest mature ggml/llama.cpp boundary
that can execute the real expert operation correctly.

## Claim boundary

This gate derives encoded GGUF tensor payload metadata. It does not measure
NVMe reads, page-cache traffic, DRAM traffic, PCIe traffic, resident RAM,
runtime allocation footprint or inference performance.
