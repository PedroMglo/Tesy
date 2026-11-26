"""Only the private, pin-checked CPU test translation unit is modified."""

from pathlib import Path
from runpy import run_path


def patch_private(src):
    run_path(str(Path(__file__).resolve().parents[1] / "overlay.py"))["patch_private"](src)
    path = src / "src/llama-moe-stream.cpp"
    data = path.read_text()
    changes = (
        (
            "void witness_capture(llama_moe_stream_layer &, int);",
            "void witness_capture(llama_moe_stream_layer &, int);\n"
            "int fixture_tile_slot(llama_moe_stream_layer &, int, int);\n"
            "void fixture_tile_publish(const llama_moe_stream_work &);",
        ),
        (
            "while ((v = pick_victim_locked(sl, sl.keep.data())) < 0)",
            "while ((v = fixture_tile_slot(sl, e, pick_victim_locked(sl, sl.keep.data()))) < 0)",
        ),
        (
            "const int32_t v = pick_victim_locked(sl, sl.keep.data());",
            "const int32_t v = fixture_tile_slot(sl, e, pick_victim_locked(sl, sl.keep.data()));",
        ),
        (
            "sl.slot_state[w.slot]=LLAMA_MOE_STREAM_SLOT_RESIDENT;",
            "sl.slot_state[w.slot]=LLAMA_MOE_STREAM_SLOT_RESIDENT;\n"
            "            fixture_tile_publish(w);",
        ),
    )
    for old, new in changes:
        if data.count(old) != 1:
            raise ValueError("C291 transition seam: " + old)
        data = data.replace(old, new)
    path.write_text(data)
