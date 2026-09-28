#!/usr/bin/env python3
"""Use the proven C35 host/model/backend preflight for the C50 server pin."""

from pathlib import Path
import c35_preflight as preflight


if __name__ == '__main__':
    preflight.ROOT = Path('results/c50-assistant-history-20260928T1042Z')
    raise SystemExit(preflight.main())
