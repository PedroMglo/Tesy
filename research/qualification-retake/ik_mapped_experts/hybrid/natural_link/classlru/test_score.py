from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

import pytest

METHOD = run_path(str(Path(__file__).with_name("score.py")))


def row(layer, ordinal=0):
    return SimpleNamespace(kind=27, call=1, tile=1, layer=layer, b=ordinal, a=0x03020100)


def test_pruned_layer_and_order():
    sample = [row(il) for il in range(35)]
    sites, initial = METHOD["t1_sites"](sample, [1])
    assert len(sites) == 35 and sites[-1][-1] == [0, 1, 2, 3] and not initial
    for bad in [sample + [row(35)], sample[::-1], sample[:-1], sample + [row(0, 1)]]:
        with pytest.raises(ValueError):
            METHOD["t1_sites"](bad, [1])


def test_cost_sign_and_last_decodes():
    sites = [(1, 9, 6, 35, []), (1, 10, 1, 35, []), (2, 46, 1, 0, []), (2, 48, 1, 0, [])]
    p = METHOD["compare"](sites, [3, 0, 3, 1], [4, 0, 1, 2])
    assert p["T1"]["saved_fills"] == -1
    assert p["T2_through_first_final"]["saved_fills"] == 2
    assert p["T2_decode"]["saved_fills"] == 1 and p["session"]["saved_payload_B"] == 0
    assert p["session"]["more_sites"] == 2
