#!/usr/bin/env python3
"""Explicit regeneration of disposable derived data, never of experimental sources."""
import argparse
from pathlib import Path
from reportlib import ROOT, EvidenceError, derive, verify

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report');p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--source-mode',choices=['snapshot','git'],default='snapshot');p.add_argument('--repo',type=Path);a=p.parse_args()
    try:
        v=verify(a.root,a.report,a.source_mode,a.repo);derive(v);print('DERIVED',a.report,v['lock']['inputs_sha256'])
    except (EvidenceError,OSError) as exc:p.exit(1,'FAIL: '+str(exc)+'\n')
if __name__=='__main__':main()
