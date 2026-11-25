"""Make a little-endian GGUF v3 from entirely artificial data using the standard library."""

import math
import struct


def string(value):
    b = value.encode()
    return struct.pack("<Q", len(b)) + b


def metadata(name, kind, value):
    if kind == 8:
        content = string(value)
    elif kind == 9:
        type_id, entries = value
        content = struct.pack("<IQ", type_id, len(entries))
        content += b"".join(
            string(x) if type_id == 8 else struct.pack({5: "<i", 6: "<f"}[type_id], x)
            for x in entries
        )
    else:
        content = struct.pack({4: "<I", 6: "<f"}[kind], value)
    return string(name) + struct.pack("<I", kind) + content


def generate(path):
    dims = {
        "context_length": 64,
        "embedding_length": 256,
        "block_count": 2,
        "expert_count": 8,
        "expert_used_count": 4,
        "feed_forward_length": 256,
        "expert_feed_forward_length": 256,
        "attention.head_count": 4,
        "attention.head_count_kv": 2,
        "attention.sliding_window": 16,
        "rope.dimension_count": 64,
        "vocab_size": 32,
    }
    kv = [
        ("general.architecture", 8, "gpt-oss"),
        ("general.name", 8, "Tesy artificial 2-layer MoE"),
        ("general.alignment", 4, 32),
        ("tokenizer.ggml.model", 8, "llama"),
        (
            "tokenizer.ggml.tokens",
            9,
            (8, ["<unk>", "<s>", "</s>", "<0x0A>"] + [f"token{i}" for i in range(4, 32)]),
        ),
        ("tokenizer.ggml.scores", 9, (6, [0.0] * 32)),
        ("tokenizer.ggml.token_type", 9, (5, [2, 3, 3, 6] + [1] * 28)),
        ("gpt-oss.attention.layer_norm_rms_epsilon", 6, 1e-5),
    ]
    kv.extend(("gpt-oss." + k, 4, v) for k, v in dims.items())
    arch = {"token_embd.weight": [256, 32], "output_norm.weight": [256], "output.weight": [256, 32]}
    for i in range(2):
        entries = {
            "attn_norm.weight": [256],
            "post_attention_norm.weight": [256],
            "attn_sinks.weight": [4],
            "ffn_gate_inp.weight": [256, 8],
            "ffn_gate_inp.bias": [8],
        }
        for r, d in (("q", 256), ("k", 128), ("v", 128), ("output", 256)):
            entries["attn_" + r + ".weight"] = [256, d]
            entries["attn_" + r + ".bias"] = [d]
        for role in ("gate", "up", "down"):
            entries["ffn_" + role + "_exps.weight"] = [256, 256, 8]
            entries["ffn_" + role + "_exps.bias"] = [256, 8]
        arch.update((f"blk.{i}." + k, v) for k, v in entries.items())
    descriptors, payload, layout = b"", bytearray(), {}
    for seed, (name, shape) in enumerate(arch.items(), 1):
        typ = 39 if "_exps.weight" in name else 0
        n = math.prod(shape)
        if typ == 39:
            # Standard MXFP4, E8M0 + 16 packed 4-bit values, one block per 32 coefficients.
            pattern = b"".join(
                bytes([121 + (seed + k) % 2])
                + bytes((seed * 19 + k * 7 + j * 17) % 256 for j in range(16))
                for k in range(127)
            )
            size = n // 32 * 17
        else:
            center = int("norm.weight" in name)
            pattern = b"".join(
                struct.pack("<f", center + (((i * 19 + seed * 31 + i * i) % 127) - 63) / 1024)
                for i in range(127)
            )
            size = n * 4
        payload.extend(bytes(-len(payload) % 32))
        offset = len(payload)
        descriptors += (
            string(name)
            + struct.pack("<I", len(shape))
            + struct.pack("<" + "Q" * len(shape), *shape)
            + struct.pack("<IQ", typ, offset)
        )
        payload.extend((pattern * (1 + size // len(pattern)))[:size])
        layout[name] = [offset, size, typ]
    header = (
        b"GGUF"
        + struct.pack("<IQQ", 3, len(arch), len(kv))
        + b"".join(metadata(*item) for item in kv)
        + descriptors
    )
    header += bytes(-len(header) % 32)
    with path.open("xb") as f:
        f.write(header)
        f.write(payload)
    return {k: [len(header) + o, n, typ] for k, (o, n, typ) in layout.items()}
