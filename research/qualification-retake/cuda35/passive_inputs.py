"""Create a local (nonpublished) ELF path/digest table for the VMA counterproof."""

import argparse
import json
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", required=True, type=Path)
    parser.add_argument("--elf-receipt", required=True, type=Path)
    parser.add_argument("--new-table", required=True, type=Path)
    args = parser.parse_args()
    libs = args.lab / "backends/c269-layer-last-use/build-c269-cuda/bin"
    exe = next(args.lab.glob("results/c236-post-c235-*/build/block-prefill-reference"))
    receipt = json.loads(args.elf_receipt.read_text())
    known = {
        r["load_name"]: r["resolved_sha256"]
        for r in receipt["selected_frozen_and_unpinned"]
        if r["load_name"].startswith(
            ("libggml", "libllama.so", "libcuda.so", "libgomp", "libstdc++", "libgcc_s")
        )
    }
    listing = subprocess.check_output(
        ["/lib64/ld-linux-x86-64.so.2", "--library-path", libs, "--list", exe], text=True
    )
    table = {}
    for line in listing.splitlines():
        if " => " in line:
            name, path = line.strip().split(" => ")
            if name in known:
                table[name] = [str(Path(path.split()[0]).resolve(strict=True)), known[name]]
    if len(known) != 9 or set(table) != set(known):
        raise ValueError("incomplete canonical ELF identity table")
    with args.new_table.open("x", encoding="utf-8") as out:
        json.dump(list(table.values()), out, indent=2)
        out.write("\n")


if __name__ == "__main__":
    main()
