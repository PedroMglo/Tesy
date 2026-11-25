import ctypes
from pathlib import Path
from runpy import run_path

measure = run_path(str(Path(__file__).with_name("measure.py")))


class Recorder:
    def __init__(self):
        self.writes = []

    def put(self, *args):
        self.writes.append(args)


def test_bank_delivers_all_roles_without_disk():
    sink = Recorder()
    scratch = bytearray(30)
    data = b"some bytes live until the worker joins"
    ptr = measure["byte_address"](data)
    assert ctypes.string_at(ptr, len(data)) == data
    assert measure["deliver"](sink, "cuda", 3, "ram", "gguf", {}, 0, ptr, scratch, -1, -1) == 0
    assert sink.writes == [("cuda", i, 3, ptr + i * measure["WEIGHT"]) for i in range(3)]


def test_direct_reads_use_absolute_payload_displacements(monkeypatch):
    logs = []
    monkeypatch.setitem(
        measure["ram"], "read_at", lambda fd, buf, n, off: logs.append((fd, n, off))
    )
    scratch = bytearray(32)
    ptr = measure["address"](scratch)
    record = {"gguf": [dict(logical=i * 4096 + i, aligned=i * 4096, count=8192) for i in range(3)]}
    sink = Recorder()
    assert (
        measure["deliver"](sink, "cpu", 2, "disk", "gguf", record, 0, 0, scratch, 19, 20)
        == 3 * 8192
    )
    assert logs == [(19, 8192, 4096 * i) for i in range(3)]
    assert sink.writes == [("cpu", i, 2, ptr + i) for i in range(3)]
