import os
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

API = run_path(str(Path(__file__).with_name("run.py")))
FIXTURE = """#!/usr/bin/python3
import os, sys
from pathlib import Path
out=Path(sys.argv[3]); out.mkdir()
(out/'maps').write_text('')
for marker in os.environ['TEST_HANDOFF'].encode():
    os.write(int(os.environ['TESY_TEST_TX']), bytes([marker]))
    if os.read(int(os.environ['TESY_TEST_RX']),1) != bytes([marker]):
        raise SystemExit(4)
"""


def test_accelerator_maps_detect_fallback(tmp_path):
    libs = [tmp_path / n for n in ("libggml.so", "libcuda.so.1", "libnvidia-extra.so")]
    for p in libs:
        p.touch()
    m = tmp_path / "maps"
    lines = [f"1-2 r--p 0 00:01 10 {p}\n" for p in libs]
    m.write_text("".join(lines[:2]))
    assert API["mapped"](m, set(map(str, libs[:2])), set()) == sorted(map(str, libs[:2]))
    for text in (lines[0], "".join(lines), "".join(lines[:2])[:-1] + " (deleted)\n"):
        m.write_text(text)
        with pytest.raises((RuntimeError, ValueError)):
            API["mapped"](m, set(map(str, libs[:2])), set())


@pytest.mark.parametrize("sequence", ["EAF", "EF"])
def test_runtime_handoff_reaps_child(tmp_path, sequence):
    exe = tmp_path / "client"
    exe.write_text(FIXTURE)
    exe.chmod(0o700)
    owners = iter([[], [None], [None], []])

    def active(pid, *args):
        current = next(owners)
        return {"gpu_owners": [pid] if current else [], "gpu": {"used_mib": 100}}

    def monitor(policy, sample):
        return {"observation": sample()}

    inv = SimpleNamespace(
        POWER={}, collect=lambda *args, **kw: {}, require_inventory=lambda *args, **kw: None
    )
    env = dict(PATH="/usr/bin:/bin", TEST_HANDOFF=sequence)
    r = {"starts": 0}
    func = API["sample_arm"]
    with patch.dict(func.__globals__, INV=inv, ACTIVE=active, IO=SimpleNamespace(monitor=monitor)):
        args = (
            "RESIDENT",
            tmp_path,
            SimpleNamespace(unit="test"),
            {"gpu": {"uuid": "gpu"}},
            datetime.now(UTC),
            exe,
            Path("unused"),
            env,
            set(),
            set(),
            r,
        )
        if sequence == "EAF":
            assert func(*args).is_dir()
            assert r["returncode"] == 0
        else:
            with pytest.raises((RuntimeError, ValueError), match="handoff order"):
                func(*args)
    assert r["child_gone"]
    with pytest.raises(ProcessLookupError):
        os.kill(r["pid"], 0)
