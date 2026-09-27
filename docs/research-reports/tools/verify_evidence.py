#!/usr/bin/env python3
"""Verify sources and, by default, exact committed derived outputs. No repairs."""
import argparse
from pathlib import Path
from reportlib import ROOT, EvidenceError, canonical, check_derived, verify

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report');p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--source-mode',choices=['snapshot','git'],default='snapshot');p.add_argument('--repo',type=Path);p.add_argument('--sources-only',action='store_true');a=p.parse_args()
    try:
        v=verify(a.root,a.report,a.source_mode,a.repo)
        if not a.sources_only: check_derived(v)
        print(canonical(v['lock']).decode(),end='')
    except (EvidenceError,OSError) as exc:p.exit(1,'FAIL: '+str(exc)+'\n')
if __name__=='__main__':main()
