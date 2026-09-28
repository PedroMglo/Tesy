#!/usr/bin/env python3
"""Fresh C35b physical preflight using the C35 inventory gate."""

from pathlib import Path

import c35_preflight as preflight


if __name__ == '__main__':
    preflight.ROOT = Path('results/c35b-template-date-20260928T0122Z')
    raise SystemExit(preflight.main())
