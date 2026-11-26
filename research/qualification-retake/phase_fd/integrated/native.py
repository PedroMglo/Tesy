"""Materialize two C269 translation units for the private PFJ1 observer."""

import argparse
import hashlib
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIN = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
SOURCES = {
    "src/llama-context.cpp": "7d8cfa9f33f38d761cf18b8e548ab7811866fbb8fdfaa95eeb2211d56851681b",
    "src/llama-moe-stream.cpp": "584aecb73900aa1164f00ec93126bc5b8b07c4d330d0f421641331b0c278d5a0",
}


def materialize(backend: Path, dest: Path) -> dict[str, Path]:
    """Write only to an empty private directory, with unchanged C269 class layout."""
    head = subprocess.check_output(["git", "-C", backend, "rev-parse", "HEAD"], text=True).strip()
    if head != PIN:
        raise ValueError("unexpected C269 source pin")
    dest.mkdir(parents=False, exist_ok=True)
    if dest.is_symlink() or any(dest.iterdir()):
        raise ValueError("overlay requires an empty destination")
    (dest / "src").mkdir()
    outputs = {}
    for name, digest in SOURCES.items():
        original = backend / name
        if original.is_symlink() or hashlib.sha256(original.read_bytes()).hexdigest() != digest:
            raise ValueError("unexpected source " + name)
        out = dest / name
        shutil.copyfile(original, out)
        outputs[name] = out
    subprocess.run(
        ["patch", "--batch", "--fuzz=0", "-p1", "-i", str(HERE / "native.patch")],
        cwd=dest,
        check=True,
        capture_output=True,
    )
    shutil.copyfile(HERE / "phase-fd-integrated.h", dest / "src/phase-fd-integrated.h")
    return outputs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir()
    materialize(args.backend, args.new_output_dir)
