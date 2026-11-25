"""Reuse the pinned C269 builder and all its 18-object closure checks for a derived main TU."""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from render import once, render  # noqa: E402

BASE_BUILD = "8ec16ede9d030e3b4c8913ca2380fe9767bb1178098bfbd1d4e9e6c027abbf8c"
SOURCES = ("schema.py", "observer.inc", "render.py", "build.py", "protocol.md")


def qualified_builder():
    path = HERE.parent / "build.py"
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != BASE_BUILD:
        raise ValueError("historical builder source")
    # Keep the historical flags, revalidate every dependency of the generated TU, use the same
    # engine for checking ELF, loader and the model-free native self-test. No backend change.
    source = once(
        data.decode(),
        '    native = HERE / "native.cpp"',
        '    native = out / "boundary.cpp"\n    native.write_bytes(render())',
    )
    source = once(
        source,
        '    need(git(REPO, "ls-files", "--error-unmatch", str(native)), '
        '"untracked native source")',
        '    for name in source_names:\n'
        '        git(REPO, "ls-files", "--error-unmatch", str(unit / name))',
    )
    source = once(
        source,
        'protocol_sha256=digest(HERE / "protocol.md")',
        'protocol_sha256=digest(unit / "protocol.md")',
    )
    ns = {
        "__name__": "boundary_qualified_builder",
        "__file__": str(path),
        "render": render,
        "unit": HERE,
        "source_names": SOURCES,
    }
    exec(compile(source, str(path), "exec"), ns)
    return ns


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ("backend", "preflight-dir", "new-output-dir"):
        ap.add_argument("--" + key, type=Path, required=True)
    a = ap.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    record = {"status": "FAIL_PRESERVED", "model_launches": 0}
    started = time.monotonic()
    try:
        base = qualified_builder()
        base["run"](a.backend, a.preflight_dir, out, record)
        record.update(
            status="PASS_FIRST_BOUNDARY_BUILD",
            inputs={k: base["digest"](HERE / k) for k in SOURCES},
            c269_startup_objects=len(record["startup_objects"]),
            original_builder_sha256=BASE_BUILD,
        )
    except Exception as exc:
        record.update(status="FAIL_PRESERVED", error=f"{type(exc).__name__}: {exc}")
    record["wall_s"] = time.monotonic() - started
    (out / "receipt.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(record["status"])
    return int(record["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
