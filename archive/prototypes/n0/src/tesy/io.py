"""Bounded strict JSON, stable regular files, and atomic no-replace results.

The caller owns the parent directory. These helpers reject existing symlinks;
they do not provide a sandbox against a hostile process renaming parent dirs.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class ContractError(ValueError):
    """Invalid input or evidence boundary. Never a scientific PASS."""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ContractError(message)


def keys(value: Any, expected: set[str], label: str) -> dict:
    require(type(value) is dict and set(value) == expected, f"{label}: key set differs")
    return value


def integer(value: Any, label: str, low: int = 0, high: int = 2**63 - 1) -> int:
    require(type(value) is int and low <= value <= high, f"{label}: integer out of bounds")
    return value


def text(value: Any, label: str, limit: int = 256) -> str:
    require(type(value) is str and 0 < len(value) <= limit and '\x00' not in value,
            f"{label}: invalid text")
    return value


def digest(value: Any, label: str = 'sha256') -> str:
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None,
            f"{label}: invalid SHA-256")
    return value


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for k, v in pairs:
        require(k not in result, f"duplicate key: {k}")
        result[k] = v
    return result


def _nonfinite(value: str) -> None:
    raise ContractError(f"non-finite JSON number: {value}")


def _check(value: Any, depth: int = 0) -> None:
    require(depth <= 32, "JSON nesting exceeds 32")
    if type(value) is float:
        require(math.isfinite(value), 'non-finite number')
    elif type(value) is dict:
        for child in value.values():
            _check(child, depth + 1)
    elif type(value) is list:
        for child in value:
            _check(child, depth + 1)


def parse_json(raw: bytes, max_bytes: int = 32 << 20) -> Any:
    require(len(raw) <= max_bytes, 'JSON byte budget exceeded')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                           parse_constant=_nonfinite)
        _check(value)
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ContractError(f'invalid JSON: {exc}') from exc


def canonical(value: Any) -> bytes:
    _check(value)
    return (json.dumps(value, sort_keys=True, allow_nan=False,
                       ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def identity(st: os.stat_result) -> tuple:
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def canonical_path(path: str | Path) -> Path:
    p = Path(os.path.abspath(path))
    require(p.resolve(strict=True) == p, 'symlink/noncanonical input path rejected')
    return p


@contextmanager
def stable_file(path: str | Path) -> Iterator[tuple[int, os.stat_result]]:
    p = canonical_path(path)
    fd = os.open(p, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode), 'input is not a regular file')
        yield fd, before
        require(identity(before) == identity(os.fstat(fd)), 'file changed during read/use')
        require(identity(before) == identity(os.stat(p, follow_symlinks=False)),
                'path replaced during read/use')
    finally:
        os.close(fd)


def read_bytes(path: str | Path, max_bytes: int = 32 << 20) -> bytes:
    with stable_file(path) as (fd, st):
        require(st.st_size <= max_bytes, 'file byte budget exceeded')
        chunks, remaining = [], st.st_size
        while remaining:
            part = os.read(fd, min(remaining, 1 << 20))
            require(bool(part), 'short read')
            chunks.append(part)
            remaining -= len(part)
        return b''.join(chunks)


def load_json(path: str | Path) -> Any:
    return parse_json(read_bytes(path))


def hash_fd(fd: int, size: int) -> str:
    h = hashlib.sha256()
    offset = 0
    while offset < size:
        part = os.pread(fd, min(8 << 20, size - offset), offset)
        require(bool(part), 'short read while hashing')
        h.update(part)
        offset += len(part)
    return h.hexdigest()


def publish(path: str | Path, value: Any) -> str:
    """Publish a fully written JSON file without overwriting any destination.

    A failure after link/fsync leaves the final file for inspection, never
    silently removes a possibly published result. Same-directory hard-link
    atomicity is supported on Linux filesystems; no rename-overwrite fallback.
    """
    p = Path(os.path.abspath(path))
    require(p.parent.resolve(strict=True) == p.parent, 'output parent must be canonical')
    raw = canonical(value)
    require(len(raw) <= 32 << 20, 'publication exceeds readback byte budget')
    fd, tmp = tempfile.mkstemp(prefix='.tesy-', dir=p.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(tmp, p, follow_symlinks=False)  # EEXIST includes dangling symlinks.
        parent_fd = os.open(p.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        require(read_bytes(p) == raw, 'publication readback differs')
        return hashlib.sha256(raw).hexdigest()
    finally:
        os.unlink(tmp)
