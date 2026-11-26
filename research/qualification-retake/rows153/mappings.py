"""Classify exact paths before inspecting the declared SONAME of any competing ELF."""

import re
import subprocess
from pathlib import Path

from vma_identity import same_vma, vma


class Guard:
    def __init__(self, refs):
        self.refs = refs
        self.by_path = {str(ref.path): name for name, ref in refs.items()}
        self.aliases = {name for name in refs} | {ref.path.name for ref in refs.values()}
        self.harmless = set()
        self.observed = set()

    def scan(self, lines):
        for line in lines:
            row = vma(line)
            if row is None:
                continue
            path = row[3]
            if path in self.by_path:
                name = self.by_path[path]
                same_vma(row[2], self.refs[name].key)
                self.observed.add(name)
                continue
            if not path.startswith("/") or (path, row[2]) in self.harmless:
                continue
            f = Path(path.removesuffix(" (deleted)"))
            if f.name in self.aliases:
                raise ValueError(f"competing ELF physical path: {f.name}")
            # Discover aliases even when the physical filename has been renamed.
            # Inspect file-backed executable segments and DSOs with data-only views.
            executable = "x" in line.split(maxsplit=2)[1]
            if not executable and ".so" not in f.name:
                continue
            if path.endswith(" (deleted)"):
                raise ValueError("unidentifiable deleted executable mapping")
            with f.open("rb") as src:
                magic = src.read(4)
            if magic == b"\x7fELF":
                output = subprocess.check_output(["readelf", "-d", f], text=True, timeout=3)
                soname = re.search(r"\(SONAME\).*\[([^]]+)\]", output)
                if soname and soname[1] in self.refs:
                    raise ValueError("competing mapped ELF SONAME: " + soname[1])
            self.harmless.add((path, row[2]))
