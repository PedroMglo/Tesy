#!/usr/bin/env python3
"""Move three verified owned build trees out of tmpfs without changing their paths."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path('results/c88-scratch-relocation-20260928T2029Z')
ARCHIVE = Path('backends/c88-archived-builds').absolute()
RECEIPT_SCHEMA = 'c88-scratch-relocation-receipt-v1'
SOURCES = [
    Path('/tmp/tesy-c15-backend-20260927/build-c33-nvtx'),
    Path('/tmp/tesy-c46-backend-20260928/build-c46-nvtx'),
    Path('/tmp/tesy-c47-backend-20260928/build-c47-skip'),
]


def meminfo():
    values = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, _, tail = line.partition(':')
        if key in ('MemAvailable', 'Shmem', 'SwapTotal', 'SwapFree'):
            amount, unit = tail.split()
            if unit != 'kB':
                raise RuntimeError(f'unexpected meminfo unit: {key}')
            values[key + '_bytes'] = int(amount) * 1024
    if len(values) != 4:
        raise RuntimeError('missing meminfo field')
    return values


def disk_free(path):
    stat = os.statvfs(path)
    return stat.f_bavail * stat.f_frsize


def size_bytes(root):
    return sum(p.lstat().st_size for p in root.rglob('*') if p.is_file() and not p.is_symlink())


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verify(source, destination):
    checked = subprocess.run(
        ['rsync', '-aHcn', '--delete', '--out-format=%n',
         str(source) + '/', str(destination) + '/'],
        capture_output=True, text=True, check=True)
    if checked.stdout.strip():
        raise RuntimeError('archive differs from tmpfs source: ' + checked.stdout[:200])


def main():
    if not ROOT.is_dir() or (ROOT/'receipt.json').exists() or ARCHIVE.exists():
        raise RuntimeError('relocation root/destination not in no-replace state')
    if any(not p.is_dir() or p.is_symlink() for p in SOURCES):
        raise RuntimeError('source must be a real directory')
    total = sum(size_bytes(p) for p in SOURCES)
    if disk_free(Path.cwd()) < total + 20 * 2**30:
        raise RuntimeError('NVMe reserve insufficient')
    receipt = {'schema': RECEIPT_SCHEMA,
               'before': meminfo(), 'source_bytes': total,
               'disk_free_before_bytes': disk_free(Path.cwd()),
               'moved': [], 'status': 'STARTED'}
    ARCHIVE.mkdir(parents=True, exist_ok=False)
    try:
        for source in SOURCES:
            destination = ARCHIVE / (source.parent.name + '__' + source.name)
            destination.mkdir(exist_ok=False)
            subprocess.run(['rsync', '-aH', str(source) + '/', str(destination) + '/'], check=True)
            verify(source, destination)
            witness = source/'bin/libggml-cuda.so.0.15.3'
            before_hash = sha(witness)
            source_staged = source.with_name(source.name + '.c88-verified-tmpfs')
            if source_staged.exists():
                raise RuntimeError('staged source collision')
            source.rename(source_staged)
            try:
                source.symlink_to(destination, target_is_directory=True)
            except Exception:
                source_staged.rename(source)
                raise
            if not source.is_dir() or sha(source/'bin/libggml-cuda.so.0.15.3') != before_hash:
                raise RuntimeError('post-link witness mismatch')
            shutil.rmtree(source_staged)
            receipt['moved'].append({'path': str(source), 'archive': str(destination),
                                     'cuda_library_sha256': before_hash})
        receipt['after'] = meminfo()
        receipt['disk_free_after_bytes'] = disk_free(Path.cwd())
        receipt['status'] = 'ARCHIVED_PATHS_PRESERVED'
    except Exception as exc:
        receipt['status'] = 'FAIL_ARCHIVAL'
        receipt['error'] = str(exc)
        receipt['after'] = meminfo()
        raise
    finally:
        with (ROOT/'receipt.json').open('x') as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write('\n')
    print(json.dumps({'status': receipt['status'],
                      'MemAvailable_delta_bytes': receipt['after']['MemAvailable_bytes'] - receipt['before']['MemAvailable_bytes'],
                      'Shmem_delta_bytes': receipt['after']['Shmem_bytes'] - receipt['before']['Shmem_bytes']}))


if __name__ == '__main__':
    main()
