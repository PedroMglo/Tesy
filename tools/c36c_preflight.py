#!/usr/bin/env python3
"""Fresh C36c physical preflight."""

from pathlib import Path

import c35_preflight as preflight


if __name__=='__main__':
    preflight.ROOT=Path('results/c36c-prefix4096-20260928T0203Z')
    raise SystemExit(preflight.main())
