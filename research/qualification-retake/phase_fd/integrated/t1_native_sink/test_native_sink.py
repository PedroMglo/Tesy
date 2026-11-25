import ctypes as ct
from pathlib import Path
from runpy import run_path
from unittest.mock import Mock

import pytest

api = run_path(str(Path(__file__).with_name("native.py")))


def test_mxfp4_tensor_header_abi():
    header = api["TensorHeader"]
    assert (header.type.offset, header.buffer.offset, header.ne.offset, header.nb.offset) == (
        0,
        8,
        16,
        48,
    )
    assert ct.sizeof(api["InitParams"]) == 24


def test_component_slot_offsets_through_the_backend_api():
    sink = api["NativeSinks"].__new__(api["NativeSinks"])
    sink.write, sink.read = Mock(), Mock()
    sink.tensors = {"cuda": (1, 2, 3)}
    address = 12345
    sink.put("cuda", 2, 39, address)
    sink.get("cuda", 1, 0, address)
    sink.write.assert_called_once_with(3, address, 39 * api["SLAB"], api["SLAB"])
    sink.read.assert_called_once_with(2, address, 0, api["SLAB"])
    for role, slot, pointer in ((-1, 1, 2), (0, 40, 2), (0, 0, 0)):
        with pytest.raises(ValueError):
            sink.put("cuda", role, slot, pointer)


def test_loaded_provider_must_match_the_verified_file(monkeypatch):
    driver = "/frozen/libcuda.so.1"
    reference = (1, 2, 3)
    p = api["Providers"].__new__(api["Providers"])
    p.handles = {"libcuda.so.1": None}
    p.paths = {"libcuda.so.1": driver}
    p.before = {(driver, reference)}
    p.vma = {driver: reference}
    p.allowed = {driver}
    p.files = {driver: {"sha256": "frozen"}}
    monkeypatch.setitem(p.check_maps.__globals__, "mapping_rows", lambda: {(driver, reference)})
    assert p.check_maps() == {"libcuda.so.1": "frozen"}
    for wrong in ({(driver, (1, 2, 99))}, {("/other/libcuda.so.1", reference)}, set()):
        monkeypatch.setitem(p.check_maps.__globals__, "mapping_rows", lambda result=wrong: result)
        with pytest.raises(ValueError):
            p.check_maps()
