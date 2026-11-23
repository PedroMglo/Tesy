#!/usr/bin/env python3
"""List report versions eligible for fail-closed automatic publication."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS_ROOT = REPOSITORY_ROOT / 'docs' / 'research-reports'
sys.path.insert(0, str(DEFAULT_REPORTS_ROOT / 'tools'))

from reportlib import EvidenceError, ID, check_derived, read, require, unique, validate, verify


def candidates(root: Path) -> list[tuple[str, str, str]]:
    """Return every registered, reviewed report version and immutable tag.

    The registry is the sole publication inventory: when a report is reviewed,
    its present and future versions are eligible without a separate manual
    enrolment. The release build remains the authoritative audit/PDF gate.
    """
    registry = read(root / 'registry.json')
    validate(root, 'registry', registry)
    registered = unique(registry['reports'])
    rows: list[tuple[str, str, str]] = []
    for report_id in registered:
        require(ID.fullmatch(report_id) is not None, 'INVALID_AUTOMATED_REPORT_ID')
        verified = verify(root, report_id)
        meta = verified['meta']
        # DRAFT reports belong in the registry so the documentation workflow can
        # verify/build previews, but release selection must not require their
        # derived/audit state. The evidence job checks drafts independently.
        if meta['editorial_state'] == 'DRAFT':
            continue
        check_derived(verified)
        audit = read(verified['folder'] / 'audit.json')
        validate(root, 'audit', audit)
        require(meta['editorial_state'] == 'REVIEWED', 'AUTO_RELEASE_REQUIRES_REVIEWED_EDITORIAL_STATE: ' + report_id)
        require(audit['status'] == 'REVIEWED', 'AUTO_RELEASE_REQUIRES_REVIEWED_AUDIT: ' + report_id)
        require(audit['inputs_sha256'] == verified['lock']['inputs_sha256'], 'AUTO_RELEASE_AUDIT_STALE: ' + report_id)
        version = meta['version']
        rows.append((report_id, version, f'reports-{report_id}-v{version}'))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_REPORTS_ROOT)
    args = parser.parse_args()
    try:
        for report_id, version, tag in candidates(args.root):
            print('\t'.join((report_id, version, tag)))
    except (EvidenceError, OSError) as exc:
        parser.exit(1, 'FAIL: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
