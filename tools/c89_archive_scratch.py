#!/usr/bin/env python3
"""Apply the frozen C88 preservation method to C48/C54 build products."""

from pathlib import Path
import c88_archive_scratch as archive

archive.ROOT = Path('results/c89-scratch-relocation-20260928T2033Z')
archive.ARCHIVE = Path('backends/c89-archived-builds').absolute()
archive.RECEIPT_SCHEMA = 'c89-scratch-relocation-receipt-v1'
archive.SOURCES = [
    Path('/tmp/tesy-c48-backend-20260928/build-c48-host'),
    Path('/tmp/tesy-c54-backend-20260928/build-c54-nvtx'),
]

if __name__ == '__main__':
    archive.main()
