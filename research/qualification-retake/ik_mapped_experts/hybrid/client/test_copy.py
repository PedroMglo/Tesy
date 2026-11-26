"""Host-only forwarding self-test for the exact interposed CUDA runtime signatures."""

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def smoke(out):
    cxx = "/usr/bin/g++-15"
    common = [cxx, "-std=c++17", "-fPIC", "-I/usr/local/cuda-13.3/include"]
    source = HERE / "test_copy.cpp"
    provider = out / "libtesy_host_abi.so"
    client = out / "test-host-hooks"
    subprocess.run(
        [*common, "-DTEST_HOST_ABI", "-shared", source, "-o", provider],
        check=True,
        timeout=20,
    )
    subprocess.run(
        [
            *common,
            "-fno-plt",
            "-rdynamic",
            source,
            HERE / "copy.cpp",
            "-L" + str(out),
            "-Wl,--no-as-needed",
            "-ltesy_host_abi",
            "-ldl",
            "-o",
            client,
        ],
        check=True,
        timeout=20,
    )
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LD_LIBRARY_PATH": str(out)}
    mapping = subprocess.check_output(["/usr/bin/ldd", client], env=env, text=True)
    if "libtesy_host_abi" not in mapping or any(
        k in mapping for k in ("libcuda", "libnvidia", "libggml")
    ):
        raise ValueError("unexpected host-test dependency")
    text = subprocess.check_output([client], env=env, text=True, timeout=5)
    lines = [row.split() for row in text.splitlines()]
    got = [(row[0], row[2] if row[0] != "REG" else None, row[-1]) for row in lines[:-1]]
    if got != [
        ("REG", None, "0"),
        ("REG", None, "1"),
        ("MEMSET", "sync", "0"),
        ("MEMSET", "async", "0"),
        ("PEER", "linear", "0"),
        ("PEER", "3d", "1"),
    ]:
        raise ValueError("registration/clear/peer witnesses")
    if lines[-1] != ["PASS_HOST_ABI_TRANSFER_PITCH_AND_RC"]:
        raise ValueError("native forwarding proof")
    return dict(
        status="PASS_HOST_ABI_TRANSFER_PITCH_AND_RC",
        cuda_driver_loaded=False,
        sha256={
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, HERE / "hooks.hpp", HERE / "copy.cpp", client, provider)
        },
    )


class Forwarding(unittest.TestCase):
    def test_host(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(smoke(Path(folder))["status"], "PASS_HOST_ABI_TRANSFER_PITCH_AND_RC")


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 3 and sys.argv[1] == "--new-output-dir":
        out = Path(sys.argv[2]).resolve()
        os.mkdir(out, 0o700)
        r = smoke(out)
        (out / "receipt.json").write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
        print(r["status"])
    else:
        unittest.main()
