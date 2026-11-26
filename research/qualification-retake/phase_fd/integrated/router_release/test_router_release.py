import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("router_floor", Path(__file__).with_name("screen.py"))
screen = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(screen)


def test_overlapping_compute_is_credited_once():
    assert screen.charge([13,2,1,1,1],5) == 8
    assert screen.charge([10]*8,30) == 0
    assert screen.charge([10]*8,3) == 17
