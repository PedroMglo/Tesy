"""Verify bank payload coverage and the public SWA range without the model."""

import re
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
KV = run_path(str(HERE.parent / "b3_numeric/kv_difference/screen.py"))
need = KV["need"]


def banks(capture):
    return KV["layers_from_log"](capture.with_suffix(".stderr").read_bytes())


def contents(path, count, layers):
    data = path.read_bytes()
    rows, _ = KV["parse"](data, count, layers)
    result = {}
    for bank in ("base", "swa"):
        positions = sorted({pos for b, kind, layer, pos in rows if b == bank})
        result[bank] = [positions[0], positions[-1], len(positions)]
    return dict(banks=result, rows=len(rows), bytes=len(data))


def snapshots(cap, mode):
    expected = {"initial.kv": 189, "entry.kv": 189, "cal-post3.kv": 192}
    if mode == "AR":
        expected.update({f"keep-{i}.kv": 189 + i for i in range(1, 6)})
    else:
        kept = 190 + int(mode[1])
        expected.update({"trim.kv": kept, "next-0.kv": kept + 1, "next-1.kv": kept + 2})
    log = cap.with_suffix(".stdout").read_text()
    records = re.findall(r"^SWA_KV (\S+) (\d+) (-?\d+) (-?\d+)$", log, re.M)
    need(len(records) == len(expected) and {r[0] for r in records} == set(expected), "KV cuts")
    layers = banks(cap)
    observed = {}
    for file, length, first, last in records:
        n, lo, hi = map(int, (length, first, last))
        need(n == expected[file] and 61 <= lo <= n - 128 and hi == n - 1, "public window")
        observed[file] = dict(public=[lo, hi], **contents(cap / file, n, layers))
    return observed
