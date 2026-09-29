#!/usr/bin/env python3
"""New trace identity with C84-matched C and C++ build flags after C122 crash."""

import argparse
from pathlib import Path
import c122_decode_trace as campaign

campaign.BUILD = campaign.BACKEND/'build-c123-cuda/bin'
campaign.ROOT_NAME = 'c123-warm153-decode-trace-20260929T1450Z'
campaign.RUN_ID = 'c123-c75-warm153'

if __name__ == '__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('mode',choices=('freeze','run'))
    ap.add_argument('root',type=Path)
    ap.add_argument('--measurement-commit')
    a=ap.parse_args();root=a.root.resolve()
    if a.mode=='freeze':campaign.freeze(root)
    else:
        if not a.measurement_commit:ap.error('run requires full SHA')
        raise SystemExit(campaign.run(root,a.measurement_commit))
