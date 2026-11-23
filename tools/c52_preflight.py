#!/usr/bin/env python3
"""Use the proven C35 host/model/backend preflight for C52."""
from pathlib import Path
import c35_preflight as preflight
if __name__ == '__main__':
    preflight.ROOT = Path('results/c52-assistant-history-sustained-20260928T1125Z')
    raise SystemExit(preflight.main())
