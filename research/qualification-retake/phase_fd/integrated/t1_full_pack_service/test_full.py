import copy
import hashlib
import os
from pathlib import Path
from runpy import run_path

import pytest

HERE = Path(__file__).resolve().parent
unit = run_path(str(HERE / "measure.py"))
bench = run_path(str(HERE.parent / "t1_primary_layout/bench.py"))


def placement():
    stat = dict(dev=1, ino=2, size=unit["SIZE"], mtime_ns=4, ctime_ns=5)
    return dict(
        status="PASS_NVME_C290_FULL_PACK_PLACEMENT",
        size_bytes=unit["SIZE"],
        source_stat=dict(stat, dev=3),
        destination_stat=stat,
        source_sha256=unit["PACK"],
        destination_sha256=unit["PACK"],
        index_sha256=unit["INDEX"],
        readback_sha256=unit["READBACK"],
        runtime_manifest_sha256=unit["RUNTIME"],
        binary_launches=0,
        source_transport="usb",
        destination_transport="nvme",
        commit="1" * 40,
        tree="2" * 40,
    )


def test_placement_rejects_compact_foreign_transport_and_aliased_file():
    positive = placement()
    assert unit["validate_placement"](positive) == list(positive["destination_stat"].values())
    for k, v in (
        ("size_bytes", 383434752),
        ("destination_sha256", "0" * 64),
        ("status", "FAIL_PRESERVED"),
        ("destination_transport", "usb"),
        ("runtime_manifest_sha256", "bad"),
        ("source_stat", positive["destination_stat"]),
    ):
        with pytest.raises(ValueError):
            unit["validate_placement"](dict(positive, **{k: v}))


def test_detect_compaction_and_wrong_key():
    stride = unit["STRIDE"]
    e = {
        (2, 5): (0, dict(layer=2, expert=5, pack_offset=261 * stride)),
        (30, 22): (unit["WINDOW"], dict(layer=30, expert=22, pack_offset=3862 * stride)),
    }
    mapped = unit["integral_entries"](e)
    assert mapped[(2, 5)][0] == 261 * stride and mapped[(30, 22)][0] == 3862 * stride
    for mutate in ("expert", "pack_offset"):
        bad = copy.deepcopy(e)
        bad[(2, 5)][1][mutate] = 0
        with pytest.raises(ValueError):
            unit["integral_entries"](bad)


def test_prepare_uses_original_offsets_and_legacy_default(monkeypatch, tmp_path):
    prepare = bench["prepare"]
    for key, size in (("WIDTH", 6), ("WEIGHT", 2), ("WINDOW", 8)):
        monkeypatch.setitem(prepare.__globals__, key, size)
    rows = [b"aabbcc", b"ddeeff"]
    # Identical payload. Poison the compact-file offsets in the full pack.
    whole = bytearray([0xEF] * 64)
    full = tmp_path / "full"
    dense = tmp_path / "dense"
    gguf = tmp_path / "gguf"
    records = []
    for i, value in enumerate(rows):
        off = 32 + 16 * i
        whole[off : off + 8] = value + b".."
        components = []
        for k in range(3):
            part = value[k * 2 : k * 2 + 2]
            start = i * 6 + k * 2
            components.append(
                dict(logical=start, aligned=start, count=2, sha256=hashlib.sha256(part).hexdigest())
            )
        records.append(dict(layer=0, expert=i, pack_offset=off, gguf=components))
    full.write_bytes(whole)
    dense.write_bytes(b"".join(x + b".." for x in rows))
    gguf.write_bytes(b"".join(rows))
    with gguf.open("rb") as g, dense.open("rb") as d, full.open("rb") as f:
        args = (None, False, lambda: None)
        base = prepare({"entries": records}, d.fileno(), g.fileno(), *args)
        new = prepare({"entries": records}, f.fileno(), g.fileno(), *args, source_offsets=True)
        assert new[:2] == base[:2]
        with pytest.raises(ValueError, match="canonical weight checksum"):
            prepare({"entries": records}, f.fileno(), g.fileno(), *args)
        with pytest.raises(ValueError, match="read-only"):
            prepare(
                {"entries": records},
                f.fileno(),
                g.fileno(),
                os.devnull,
                True,
                lambda: None,
                source_offsets=True,
            )
