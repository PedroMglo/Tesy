#!/usr/bin/env python3
"""Fresh C37 physical preflight using isolated backend inventory."""

from pathlib import Path

import c35_preflight as preflight


if __name__=='__main__':
    preflight.ROOT=Path('results/c37-session-retention-20260928T0226Z')
    raise SystemExit(preflight.main())
