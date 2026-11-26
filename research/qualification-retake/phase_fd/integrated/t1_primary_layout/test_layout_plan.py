from pathlib import Path
from runpy import run_path

import pytest

plan = run_path(str(Path(__file__).with_name("plan.py")))


def test_bank_and_resident_are_distinct_sources():
    pool = plan["causal"]["Pool"]([1, 2])
    assert plan["origins"](pool, 0, [1, 3, 4], {(0, 3), (1, 4)}) == ["primary", "ram", "disk"]


def test_index_must_cover_the_canonical_expert():
    size = 4406400
    entries = [
        dict(
            name=f"blk.0.ffn_{role}_exps.weight",
            type="mxfp4",
            size_bytes=size,
            packed_relative_offset=i * size,
            source_offset=20_000_000 * i + 500,
            sha256="00" * 32,
        )
        for i, role in enumerate(("gate", "down", "up"))
    ]
    index = dict(
        experts=[dict(layer=0, tier="CPU", expert=0, pack_offset=0, components=entries)],
        weight_window=13221888,
        pack_bytes=13258752,
        stride=13258752,
    )
    meta = {(0, i): (20_000_000 * i + 500, size) for i in range(3)}
    assert plan["bind"](0, 0, index, meta)["gguf"][0]["aligned"] == 0
    entries[1]["source_offset"] += 1
    with pytest.raises(ValueError, match="weight slice"):
        plan["bind"](0, 0, index, meta)
