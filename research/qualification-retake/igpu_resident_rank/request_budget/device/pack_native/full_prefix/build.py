"""Build the full-prefix ELF against the authenticated C291 control."""

import hashlib
import subprocess
from pathlib import Path
from runpy import run_path
from types import FunctionType

HERE = Path(__file__).resolve().parent
BASE = run_path(str(HERE.parent / "dso/build.py"))
SOURCE = "bc622a0ab63c8270a2701be138b64c8286f39a6e48528e02726dd48a4d93ba1a"
HEADER = "b65465f18920b2c9b62e30cc9b3d443c17fe38a1d240bfef6f87078904e4e6ff"
CONTROL = "772740127a1227afae0b0325d0b186f35e1c7e428d6929181019bb8c455b6b25"
PARENT = "cfd616fda7fcdac7aaf6774f9b6d2aac7ea5186a5629fa33eb1bff58a00b34c8"
PROTOCOL = "94cb404606b354935381ec3001fa76e8fa803c29ee884e71781bf303e582330c"
need = BASE["need"]


def bind(fn, **replacements):
    return FunctionType(
        fn.__code__, fn.__globals__ | replacements, fn.__name__, fn.__defaults__, fn.__closure__
    )


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def patch_source(src):
    head = src / "phase-fd-integrated.h"
    need(sha(head) == SOURCE, "parent packed observer header")
    subprocess.run(
        [
            "/usr/bin/patch",
            "--batch",
            "--forward",
            "--fuzz=0",
            "-p1",
            "-i",
            str(HERE / "profile.patch"),
        ],
        cwd=src.parent,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        check=True,
        capture_output=True,
        timeout=10,
    )
    need(sha(head) == HEADER, "derived header")
    return src


def sources(backend, directory):
    return patch_source(BASE["private_sources"](backend, directory))


def run(a, out, r):
    need(sha(HERE / "protocol.md") == PROTOCOL and a.intact_receipt, "protocol/build control")
    bind(BASE["run"], private_sources=sources)(a, out, r)
    need(
        r["status"] == "PASS_C291_PACK_PFJ_DSO_STATIC_C281"
        and r["control_sha256"] == CONTROL
        and r["header_sha256"] == HEADER,
        "known control and private profile",
    )
    r.update(
        status="PASS_C291_FULL_PREFIX_DSO_STATIC_C281",
        parent_build_sha256=PARENT,
        profile_header_sha256=HEADER,
        profile_patch_sha256=sha(HERE / "profile.patch"),
        profile_protocol_sha256=PROTOCOL,
        profile_builder_sha256=sha(__file__),
        capacity=1_398_100,
        cut_call=86,
    )


if __name__ == "__main__":
    raise SystemExit(bind(BASE["main"], run=run)())
