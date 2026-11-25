import importlib.util
import itertools
import os
from functools import lru_cache
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "pfj_conservation", Path(__file__).with_name("analyse.py")
)
pfj = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pfj)


def one_tile():
    rows = []

    def add(event, **fields):
        values = dict.fromkeys(pfj.Row._fields, 0)
        values.update(call=1, tile=-1, wave=-1, ns=len(rows) + 1, kind=pfj.NAMES.index(event))
        rows.append(pfj.Row(**(values | fields)))

    add("ENTER", a=1)
    add("FILE", fd=4, a=2, b=3, c=os.O_DIRECT)
    for layer in range(36):
        for slot in range(40):
            add("SLOT", layer=layer, slot=slot, expert=slot, a=2)
        for component in range(3):
            add("WEIGHT", layer=layer, component=component, fd=4, b=4096)
    add("TILE", tile=1, a=1)
    for layer in range(36):
        site = {"tile": 1, "layer": layer}
        add("REMAP_BEGIN", a=1, b=4, **site)
        add("RANKS", a=0x03020100, **site)
        for k in range(4):
            add("DEMAND", slot=k, expert=k, **site)
        add("BARRIER_ENTER", **site)
        add("BARRIER_RETURN", **site)
        add("REMAP_END", **site)
    add("TILE_RETURN", tile=1)
    add("RETURN")
    for worker in range(4):
        add("WORKER_EXIT", worker=worker, call=0)
    add("END", call=0)
    return rows, {"records": len(rows), "flags": 1}


def test_complete_and_corrupt_warm_tile():
    rows, header = one_tile()
    assert pfj.audit(rows, header)["status"] == "PASS"
    i = next(i for i, e in enumerate(rows) if e.kind == 10)
    rows[i] = rows[i]._replace(gen=7)
    assert pfj.audit(rows, header)["gate"] == "demand generation"


def test_relaxation_matches_exhaustive_optimum():
    for sequence in itertools.product(range(3), repeat=5):

        @lru_cache
        def opt(i, cache, sequence=sequence):
            if i == len(sequence):
                return 0
            e = sequence[i]
            if e in cache:
                return opt(i + 1, cache)
            return 1 + min(opt(i + 1, (cache - {old}) | {e}) for old in cache)

        assert pfj.belady(sequence, {1, 2}, slots=2) == opt(0, frozenset({1, 2}))


def test_overlap_and_gaps():
    assert pfj.union_ns([(1, 4), (2, 3), (4, 7), (9, 10)]) == 7
