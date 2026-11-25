"""Restrict the fixture hook to the private C291 worker translation unit."""

from pathlib import Path


def materialize(src: Path) -> None:
    path = src / "src/llama-moe-stream.cpp"
    text = path.read_text()

    def one(before, after):
        nonlocal text
        if text.count(before) != 1:
            raise ValueError("unexpected C291 worker source")
        text = text.replace(before, after)

    one('#include "ggml-backend.h"', '#include "ggml-backend.h"\n#include "lease.h"')
    start = text.index("            if (expert_store) {", text.index("::worker_loop()"))
    end = text.index("        } catch (const std::exception", start)
    one(text[start:end], "            ok = lease_prepare(w);\n")
    one(
        "        const bool valid=tesy_store_completion_valid",
        "        lease_wait(w, lk, ok);\n        const bool valid=tesy_store_completion_valid",
    )
    one(
        "            sl.slot_state[w.slot]=LLAMA_MOE_STREAM_SLOT_RESIDENT;",
        "            lease_install(w);\n            sl.slot_state[w.slot]=LLAMA_MOE_STREAM_SLOT_RESIDENT;",
    )
    one("        cv_done.notify_all();", "        lease_end();\n        cv_done.notify_all();")
    path.write_text(text)
