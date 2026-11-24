"""Read-only VMA identity for a checked open ELF, independent of stat device encoding."""

import ctypes
import hashlib
import os
from pathlib import Path


def vma(line):
    parts = line.split(maxsplit=5)
    if len(parts) != 6:
        return None
    start, end = [int(s, 16) for s in parts[0].split("-")]
    major, minor = [int(s, 16) for s in parts[3].split(":")]
    return start, end, (major, minor, int(parts[4])), parts[-1]


def stable(st):
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def same_vma(actual, expected):
    if actual != expected:
        raise ValueError("mapped ELF VMA identity differs")


class Reference:
    def __init__(self, stack, path, digest):
        self.path = Path(path).resolve(strict=True)
        self.file = stack.enter_context(self.path.open("rb"))
        self.identity = stable(os.fstat(self.file.fileno()))
        self.digest = digest
        self.verify()
        libc = ctypes.CDLL(None, use_errno=True)
        libc.mmap.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_long,
        ]
        libc.mmap.restype = ctypes.c_void_p
        libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        page = os.sysconf("SC_PAGE_SIZE")
        # Linux PROT_READ=1, MAP_PRIVATE=2. A single page suffices; never executed.
        ptr = libc.mmap(None, page, 1, 2, self.file.fileno(), 0)
        if ptr == ctypes.c_void_p(-1).value:
            raise OSError(ctypes.get_errno(), "mmap read-only ELF identity")
        stack.callback(libc.munmap, ptr, page)
        rows = [vma(line) for line in Path("/proc/self/maps").read_text().splitlines()]
        (mapping,) = [row for row in rows if row and row[0] <= ptr < row[1]]
        self.key, name = mapping[2], mapping[3]
        if name != str(self.path) or self.key[2] != self.identity[1]:
            raise ValueError("passive VMA does not identify the verified FD")

    def verify(self):
        self.file.seek(0)
        if (
            stable(os.fstat(self.file.fileno())) != self.identity
            or stable(self.path.stat()) != self.identity
            or hashlib.file_digest(self.file, "sha256").hexdigest() != self.digest
        ):
            raise ValueError("open ELF FD, path or digest changed")
