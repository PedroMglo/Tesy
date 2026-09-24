import json

import pytest

from tesy.vertical_evidence_bundle import _check_text, sanitize_doctor


def test_sanitize_doctor_omits_unrelated_mount_enumeration():
    raw = json.dumps({
        "reference_check": {"status": "PASS"},
        "snapshot": {
            "virtualization": {"status": "PHYSICAL"},
            "storage_topology": {
                "findmnt": {"stdout": "/dev/nvme0n1p3"},
                "lsblk": {"stdout": "/home/user/unrelated-private-mount"},
            },
        },
    }).encode()
    public, note = sanitize_doctor(raw)
    decoded = json.loads(public)
    assert "lsblk" not in decoded["snapshot"]["storage_topology"]
    assert decoded["snapshot"]["storage_topology"]["findmnt"]["stdout"]
    assert note["was_present"] is True
    assert b"unrelated-private-mount" not in public


def test_bundle_text_scan_rejects_unrelated_home_path():
    with pytest.raises(ValueError, match="unrelated home path"):
        _check_text(
            b"/home/pmglo/private-thing",
            allowed_prefixes=("/home/pmglo/Projects/Tesy/",),
            name="test",
        )


def test_bundle_text_scan_allows_tesy_path():
    _check_text(
        b"/home/pmglo/Projects/Tesy/results/example",
        allowed_prefixes=("/home/pmglo/Projects/Tesy/",),
        name="test",
    )
