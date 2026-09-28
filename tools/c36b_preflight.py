#!/usr/bin/env python3
"""Fresh C36b physical preflight for the corrected campaign."""

from pathlib import Path

import c35_preflight as preflight


if __name__=='__main__':
    preflight.ROOT=Path('results/c36b-prefix4096-20260928T0155Z')
    raise SystemExit(preflight.main())
