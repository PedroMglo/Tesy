#!/usr/bin/env python3
"""Use the proven C35 host/model/backend preflight for C54."""
from pathlib import Path
import c35_preflight as preflight
import c54_warm_phase as campaign
if __name__ == '__main__':
    preflight.ROOT = campaign.ROOT
    preflight.BACKEND = campaign.BACKEND
    preflight.BINARY = campaign.BINARY
    raise SystemExit(preflight.main())
