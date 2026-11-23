#!/usr/bin/env python3
"""Fresh C36 physical preflight using the isolated backend inventory."""

from pathlib import Path

import c35_preflight as preflight


if __name__ == '__main__':
    preflight.ROOT=Path('results/c36-prefix4096-20260928T0153Z')
    raise SystemExit(preflight.main())
