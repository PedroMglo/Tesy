"""Test-only source seams inside two C291 primitives, checked against their Git tree."""

from pathlib import Path


def patch_private(src: Path):
    f = src / "src" / "llama-moe-stream.cpp"
    s = f.read_text()
    reserve = (
        "void llama_moe_stream::reserve_slot_locked("
        "llama_moe_stream_layer & sl, int32_t expert, int32_t slot) {"
    )
    changes = [
        (
            '#include "llama-moe-stream.h"',
            '#include "llama-moe-stream.h"\n'
            "#ifndef TESY_STORE_TESTING\n#error fixture-only source\n#endif\n"
            "void witness_capture(llama_moe_stream_layer &, int);\n"
            "const uint8_t *witness_lookup(const llama_moe_stream_work &);\n"
            "void witness_claim(const llama_moe_stream_work &, const uint8_t *);",
        ),
        (
            "sl.slot_claimed[w.slot] = 1;\n\n        lk.unlock();",
            "sl.slot_claimed[w.slot] = 1;\n"
            "        const uint8_t *const bank = witness_lookup(w);\n"
            "        lk.unlock();\n        witness_claim(w, bank);",
        ),
        (
            "const uint8_t *data=expert_store->read(sl.il,w.expert,staging);",
            "const uint8_t *data=bank ? bank : expert_store->read(sl.il,w.expert,staging);",
        ),
        (
            "if(expert_store){stats.n_store_loads++;",
            "if(expert_store && !bank){stats.n_store_loads++;",
        ),
        (
            reserve,
            reserve + "\n    witness_capture(sl,slot);",
        ),
    ]
    for before, after in changes:
        if s.count(before) != 1:
            raise ValueError(f"C291 seam mismatch: {before!r}")
        s = s.replace(before, after)
    f.write_text(s)
