"""Private worker, rank, reservation and publication seams on an authenticated C291 source."""

from pathlib import Path

HERE = Path(__file__).resolve().parent


def install(private):
    src = private / "src"
    (src / "selector.h").write_bytes((HERE / "selector.h").read_bytes())
    path = src / "llama-moe-stream.cpp"
    text = path.read_text()

    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError(f"C291 source seam {old!r}")
        text = text.replace(old, new)

    def append(old, new):
        replace(old, old + "\n" + new)

    append(
        '#include "ggml-backend.h"',
        """#ifndef TESY_STORE_TESTING
#error private retained-delivery fixture only
#endif
#include "selector.h"
void retained_rank(llama_moe_stream_layer &, const int32_t *, int64_t);
void retained_offer(llama_moe_stream_layer &, int);
retained::Lease retained_claim(const llama_moe_stream_work &);
void retained_publish(const llama_moe_stream_work &);""",
    )
    append("sl.slot_claimed[w.slot] = 1;", "        auto lease = retained_claim(w);")
    replace(
        "const uint8_t *data=expert_store->read(sl.il,w.expert,staging);",
        "const uint8_t *data=lease ? lease->data() : expert_store->read(sl.il,w.expert,staging);",
    )
    replace(
        "if(expert_store){stats.n_store_loads++;",
        "if(expert_store && !lease){stats.n_store_loads++;",
    )
    append(
        "sl.slot_state[w.slot]=LLAMA_MOE_STREAM_SLOT_RESIDENT;", "            retained_publish(w);"
    )
    signature = "void llama_moe_stream::reserve_slot_locked("
    args = "llama_moe_stream_layer & sl, int32_t expert, int32_t slot) {"
    append(signature + args, "    retained_offer(sl, slot);")
    replace(
        "    mgr->stats.n_calls++;", "    retained_rank(*sl, ids, n);\n    mgr->stats.n_calls++;"
    )
    wavezero = "        mgr->plan_waves_locked(*sl, ids, n);"
    replace(wavezero, "        retained_rank(*sl, ids, n);\n" + wavezero)
    path.write_text(text)
