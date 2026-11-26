"""Passive counterproof for canonical path and renamed competing Fedora ELF."""

import argparse
import hashlib
import json
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path


def main(repo, lab):
    sys.path.insert(0, str(repo / "research/qualification-retake/cuda35"))
    import layer
    from mappings import Guard
    from vma_identity import Reference

    known = layer.read(repo / "research/qualification-retake/cuda35/receipts/r3.json")[
        "resolved_elf_sha256"
    ]
    lib = lab / "backends/c269-layer-last-use/build-c269-cuda/bin"
    exe = next(lab.glob("results/c236-post-c235-*/build/block-prefill-reference"))
    with ExitStack() as stack:
        refs = {}
        for line in layer.shell(
            "/lib64/ld-linux-x86-64.so.2", "--library-path", str(lib), "--list", str(exe)
        ).splitlines():
            if " => " in line:
                name, path = line.strip().split(" => ")
                if name in known:
                    refs[name] = Reference(stack, Path(path.split()[0]), known[name])
        guard = Guard(refs)
        rows = Path("/proc/self/maps").read_text().splitlines()
        guard.scan(rows)
        if guard.observed != set(known):
            raise ValueError("missing positive DSO")
        old_filter = {name.split(".so")[0] + ".so" for name in known}
        missed = [
            name
            for name, ref in refs.items()
            if ref.path.name.split(".so")[0] + ".so" not in old_filter
        ]
        if missed != ["libgcc_s.so.1"]:
            raise ValueError("R1 counterexample not reproduced")
        name = "libgcc_s.so.1"
        other = Path(stack.enter_context(tempfile.TemporaryDirectory())) / "other-fixture.so"
        payload = refs[name].path.read_bytes()
        other.write_bytes(payload)
        extra = Reference(stack, other, hashlib.sha256(payload).hexdigest())
        if extra.key == refs[name].key:
            raise ValueError("negative control did not change inode")
        try:
            guard.scan(Path("/proc/self/maps").read_text().splitlines())
        except ValueError as exc:
            if str(exc) != "competing mapped ELF SONAME: libgcc_s.so.1":
                raise
            print(
                json.dumps(
                    {
                        "canonical_vmas": sorted(guard.observed),
                        "r1_omitted": missed,
                        "renamed_duplicate": "REJECTED",
                        "target_file_opens": 0,
                        "gpu_calls": 0,
                    }
                )
            )
            return
        raise ValueError("accepted another mapped inode with the same ELF SONAME")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--lab", type=Path, required=True)
    a = ap.parse_args()
    main(a.repo, a.lab)
