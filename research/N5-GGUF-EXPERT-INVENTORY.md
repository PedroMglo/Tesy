# N5 GGUF encoded expert inventory

Date: 2026-09-23
Status: IMPLEMENTED / REAL_MODEL_NOT_RUN

## Purpose

Count-space cache headroom is insufficient for a byte-oriented systems claim.
Before a native cache is designed, Tesy needs a model-specific inventory of the
encoded expert payload.

The pinned llama.cpp source includes `gguf-py`. Its `GGUFReader` exposes, for
each tensor, the logical shape, encoded `n_bytes` and absolute tensor
`data_offset`.

For merged MoE tensors in llama.cpp, names such as:

```text
blk.N.ffn_gate_exps.weight
blk.N.ffn_up_exps.weight
blk.N.ffn_down_exps.weight
```

carry the expert count in the final logical GGUF dimension.

## Admitted derivation

For each merged `*_exps` tensor, Tesy admits:

```text
encoded_payload_bytes_per_expert =
    tensor.n_bytes / tensor.shape[-1]
```

**only when the division is exact** and all merged expert tensors in the layer
agree on the expert count.

Any mismatch produces `INCONCLUSIVE`; there is no inferred correction.

## What this does not mean

Even a `PASS_DERIVATION` does not establish:
- one contiguous physical read per expert;
- page-cache miss bytes;
- NVMe device bytes;
- DRAM traffic;
- RAM->GPU traffic;
- CUDA allocation footprint;
- transfer granularity used by llama.cpp.

Those require runtime/OS/device evidence.

## Physical-host command

After the locked model is installed and the pinned source checkout exists:

```bash
source .venv/bin/activate
bash scripts/bootstrap_gguf_tools.sh

tesy models inventory-experts \
  gpt-oss-20b-mxfp4-gguf \
  ~/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf \
  --llama-source .deps/llama.cpp \
  > results/gpt-oss-20b-expert-inventory.json
```

Use a new absent result path. The model verifier runs before the inventory and
therefore rechecks the locked filename/size/SHA.

## Next use

Only after the real inventory passes should native routing traces be converted
from equal-sized slots into encoded-byte-weighted cache simulations.

The first byte-weighted result is still `TRACE_DERIVED`, not measured I/O.
