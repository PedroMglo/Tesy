"""CI synthetic parser inputs; optionally replay archived stock evidence without a forward."""

import argparse
import importlib.util
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import attribution as attr
from test_attribution import witness

ATTR_R1_RECEIPT = "c6e4cc074c449023f4f5adad56114dd55013773836ccef54ce113cd8791e89e1"
ATTR_R1_STDOUT = "2fb3808631148857b639e90efcba80622057324e7c650d7471e467098496e1a4"


def synthetic(root):
    stock = root / "reference"
    overlay = root / "overlay"
    libs = stock / "build/bin"
    libs.mkdir(parents=True)
    candidate = overlay / "candidate/libllama.so.0"
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes(b"candidate test image")
    original = libs / "libllama.so.0.9.0"
    original.write_bytes(b"reference test image")
    (libs / "libllama.so.0").symlink_to(original)
    names = ["libggml.so.0", "libggml-cpu.so.0", "libggml-base.so.0", "libggml-cuda.so.0"]
    for name in names:
        (libs / name).write_bytes(name.encode())
    digests = {name: attr.guard.sha(libs / name) for name in names}
    original_hash = attr.guard.sha(original)
    (overlay / "receipt.json").write_text(
        json.dumps(
            dict(
                status="PASS_PRIVATE_GOLD_AND_CANDIDATE_BUILD",
                original_sha256=original_hash,
                stock_dsos=digests,
                phases={
                    "gold": {"sha256": original_hash},
                    "candidate": {"sha256": attr.guard.sha(candidate)},
                },
            )
        )
    )
    model = b"synthetic parser input"
    log = "\n".join(
        [
            f"LIB {original}",
            f"MAP {len(model)} 0 1 32769",
            f"ADVICE 0 {len(model)} 3 0",
            witness(libs),
            "CPU_MATMUL 16 0",
            *[f"ELF {libs / n}" for n in names],
            f"ELF {original}",
            "",
        ]
    )
    logits = struct.pack("<64f", *range(32), *reversed(range(32)))
    return stock, overlay, model, log, logits


def read_archived(archive, stock, overlay):
    guard = attr.guard
    for path, expected in (
        (archive / "receipt.json", ATTR_R1_RECEIPT),
        (archive / "stock/stdout", ATTR_R1_STDOUT),
        (archive / "stock/logits.f32", attr.R1_LOGITS),
        (archive / "tiny.gguf", guard.GGUF_SHA),
        (overlay / "receipt.json", guard.BUILD_SHA),
    ):
        guard.require(guard.sha(path) == expected, "archived input hash " + path.name)
    return (
        stock,
        overlay,
        (archive / "tiny.gguf").read_bytes(),
        (archive / "stock/stdout").read_text(),
        (archive / "stock/logits.f32").read_bytes(),
    )


def replay(root, inputs, fix):
    stock, overlay, model, log, logits = inputs
    out = root / ("fixed" if fix else "original")
    out.mkdir()
    old = root / "r1"
    (old / "stock").mkdir(parents=True, exist_ok=True)
    (old / "stock/logits.f32").write_bytes(logits)
    libs = stock / "build/bin"
    tiny_path = attr.guard.UPSTREAM / "tiny_fixture.py"
    spec = importlib.util.spec_from_file_location("tesy_tiny_replay", tiny_path)
    tiny = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tiny)
    receipt = {}
    if fix:
        receipt["repaired_function_sha256"] = attr.repair_check_run(tiny)
    tiny.mapped = attr.extend_mapping_check(tiny.mapped, out, receipt, old, libs)
    original = libs / "libllama.so.0.9.0"
    candidate = (overlay / "candidate/libllama.so.0").resolve()
    modes = []

    def prerecorded(argv, **kw):
        if argv[0] == "/usr/bin/g++":
            Path(argv[-1]).write_bytes(b"no native process or compilation")
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        name = Path(argv[2]).parent.name
        modes.append(name)
        text = log
        if name != "stock":
            # Derived fixtures solely for parsing the remaining control paths.
            text = (
                "\n".join(
                    f"LIB {candidate}"
                    if line.startswith("LIB ")
                    else f"ELF {candidate}"
                    if line.startswith("ELF ") and Path(line[4:]).resolve() == original
                    else line
                    for line in log.splitlines()
                )
                + "\n"
            )
        if name == "invalid":
            return subprocess.CompletedProcess(
                argv, 25, f"LIB {candidate}\n".encode(), b"TESY_STOCK_LAZY_MMAP"
            )
        if name == "ON":
            text = (
                "\n".join(
                    line.replace(" 0 1 32769", " 0 1 1") if line.startswith("MAP ") else line
                    for line in text.splitlines()
                    if not line.startswith("ADVICE ")
                )
                + "\n"
            )
        Path(argv[2]).write_bytes(logits)
        return subprocess.CompletedProcess(argv, 0, text.encode(), b"")

    def fake_source_writer(_src, path):
        path.write_bytes(model)

    with (
        patch.object(tiny, "make_model", fake_source_writer),
        patch.object(tiny.subprocess, "check_output", side_effect=[tiny.PIN, ""]),
        patch.object(tiny.subprocess, "run", side_effect=prerecorded),
    ):
        if not fix:
            try:
                tiny.check_run(stock, overlay, out, receipt)
            except TypeError as exc:
                # The actual invocation reaches the integer call before entering mapped().
                frame = exc.__traceback__
                while frame.tb_next is not None:
                    frame = frame.tb_next
                import linecache

                line = linecache.getline(frame.tb_frame.f_code.co_filename, frame.tb_lineno)
                attr.guard.require(
                    "model.stat().st_size()" in line and modes == ["stock"],
                    "different fault before stock parser",
                )
                return receipt
            raise AssertionError("original integer invocation was not rejected")
        status = tiny.check_run(stock, overlay, out, receipt)
    attr.guard.require(
        status == attr.guard.SUCCESS and modes == ["stock", "OFF", "ON", "invalid"],
        "incomplete full parser replay",
    )
    for name in modes[:3]:
        arm = receipt["arms"][name]
        attr.guard.require(
            arm["cpu_matmuls"] == 16
            and len(arm["execution_by_prompt"]) == 2
            and arm["logits_compared"] == 64
            and len(arm["mapped_elf_sha256"]) == 5
            and len(arm["greedy_ids"]) == 2
            and bool(arm["advice"]) == (name != "ON"),
            "stock/derived parser postconditions",
        )
    return receipt


class ReplayTests(unittest.TestCase):
    def test_full_original_failure_and_all_repaired_arms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = synthetic(root)
            replay(root, inputs, False)
            replay(root, inputs, True)


if __name__ == "__main__":
    if "--archived-run" in sys.argv:
        p = argparse.ArgumentParser()
        for arg in ("archived-run", "stock-build-root", "overlay-root"):
            p.add_argument("--" + arg, required=True, type=Path)
        a = p.parse_args()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = read_archived(a.archived_run, a.stock_build_root, a.overlay_root)
            replay(root, inputs, False)
            r = replay(root, inputs, True)
            print("PASS_ARCHIVED_STOCK_AND_DERIVED_PARSER_FIXTURES", r["repaired_function_sha256"])
    else:
        unittest.main()
