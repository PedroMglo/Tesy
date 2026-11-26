"""Verify native GGML INFO visibility against the exact stock common library."""

import argparse
import ctypes
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stock_startup"))
from start import check, logged_geometry, sha  # noqa: E402

MESSAGES = [
    "fixture: CPU_Mapped model buffer size = 1.00 MiB",
    "fixture: CUDA0 MoE cache size = 1.00 MiB",
    "fixture: 36 layers, mxfp4: 161 slots",
    "fixture: creating non-SWA KV cache, size = 8192 cells",
    "fixture: creating     SWA KV cache, size = 256 cells",
]
FIELDS = {"mapped", "cuda", "group", "full_kv", "swa_kv"}


def emit(lib, level):
    dll = ctypes.CDLL(str(lib))
    main = dll._Z15common_log_mainv
    main.restype = ctypes.c_void_p
    set_level = dll._Z30common_log_set_verbosity_tholdi
    set_level.argtypes = [ctypes.c_int]
    set_level.restype = None
    get_level = dll._Z24common_log_get_verbosity14ggml_log_level
    get_level.argtypes = [ctypes.c_int]
    get_level.restype = ctypes.c_int
    callback = dll._Z27common_log_default_callback14ggml_log_levelPKcPv
    callback.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p]
    callback.restype = None
    flush = dll._Z16common_log_flushP10common_log
    flush.argtypes = [ctypes.c_void_p]
    flush.restype = None
    ggml_info = 2
    check(get_level(ggml_info) == 4, "upstream_GGML_INFO_mapping")
    set_level(level)
    for message in MESSAGES:
        callback(ggml_info, (message + "\n").encode(), None)
    flush(main())


def verify(lib, build_receipt, output):
    output.mkdir(exist_ok=False)
    rec = {"status": "FAIL", "scope": "NATIVE_LOGGER_MODEL_FREE", "forwards": 0}
    try:
        b = json.loads(build_receipt.read_text())
        check(
            b["decision"] == "PASS_STOCK_BUILD_AND_MODEL_FREE_CLI"
            and sha(lib) == b["own_libs_sha256"]["libllama-common.so.0"],
            "stock_common",
        )
        rec["common_sha256"] = sha(lib)
        rec["build_receipt_sha256"] = sha(build_receipt)
        rec["protocol_sha256"] = sha(HERE / "protocol.md")
        rec["by_verbosity"] = {}
        for level in (3, 4):
            proc = subprocess.run(
                [sys.executable, __file__, "--emit", str(level), "--library", str(lib)],
                capture_output=True,
                timeout=10,
                check=True,
                env={**os.environ, "CUDA_VISIBLE_DEVICES": "", "LD_LIBRARY_PATH": str(lib.parent)},
            )
            observed = (proc.stdout + proc.stderr).decode()
            found = {k for k, v in logged_geometry(observed).items() if v}
            check(found == (set() if level == 3 else FIELDS), "verbosity_" + str(level))
            rec["by_verbosity"][str(level)] = sorted(found)
        rec["status"] = "PASS_GGML_INFO_IS_LEVEL_4"
    finally:
        pending = output / ".receipt.pending"
        pending.write_text(json.dumps(rec, sort_keys=True, indent=2) + "\n")
        pending.rename(output / "receipt.json")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--library", required=True, type=Path)
    p.add_argument("--emit", type=int, choices=[3, 4])
    p.add_argument("--build-receipt", type=Path)
    p.add_argument("--new-output", type=Path)
    a = p.parse_args()
    if a.emit is None:
        if not a.build_receipt or not a.new_output:
            p.error("verification requires --build-receipt and --new-output")
        verify(a.library.resolve(), a.build_receipt, a.new_output)
    else:
        emit(a.library.resolve(), a.emit)
