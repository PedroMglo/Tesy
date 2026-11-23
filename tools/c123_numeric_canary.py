#!/usr/bin/env python3
"""Matched-flag C123 canary; C122 segfault artifacts stay unchanged."""

import argparse
from pathlib import Path
import c123_decode_trace as wrapper
import c122_numeric_canary as canary

canary.campaign.BUILD=wrapper.campaign.BUILD
canary.BIN=wrapper.campaign.BUILD/'c123_session_boundary_capture'
canary.RUN_ID='c123-numeric-canary-on01'

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('freeze','run'))
    ap.add_argument('root',type=Path);ap.add_argument('--measurement-commit')
    a=ap.parse_args();root=a.root.resolve()
    if a.mode=='freeze':canary.freeze(root)
    else:
        if not a.measurement_commit:ap.error('run needs full SHA')
        raise SystemExit(canary.run(root,a.measurement_commit))
