import json
import subprocess
import sys
from pathlib import Path

import pytest

from tesy.process_identity import (
    ProcessIdentityError,
    collect_process_identity,
)


def _write_argv(path: Path, argv: list[str]) -> None:
    path.write_text(json.dumps(argv), encoding="utf-8")


def test_process_identity_binds_live_executable_and_argv(tmp_path):
    command = [
        sys.executable,
        "-c",
        "import time; time.sleep(2)",
    ]
    expected = tmp_path / "argv.json"
    _write_argv(expected, command)

    process = subprocess.Popen(command)
    try:
        result = collect_process_identity(
            pid=process.pid,
            expected_executable=Path(sys.executable),
            expected_argv_path=expected,
        )
    finally:
        process.terminate()
        process.wait(timeout=5)

    assert result["status"] == "PASS"
    assert result["argv"]["status"] == "PASS"
    assert result["executable"]["sha256"]


def test_process_identity_reports_exact_argv_mismatch(tmp_path):
    command = [
        sys.executable,
        "-c",
        "import time; time.sleep(2)",
    ]
    expected = tmp_path / "argv.json"
    _write_argv(expected, [*command, "unexpected"])

    process = subprocess.Popen(command)
    try:
        result = collect_process_identity(
            pid=process.pid,
            expected_executable=Path(sys.executable),
            expected_argv_path=expected,
        )
    finally:
        process.terminate()
        process.wait(timeout=5)

    assert result["status"] == "FAIL"
    assert result["argv"]["status"] == "FAIL"
    assert result["mismatches"] == [
        "process argv does not exactly match frozen argv"
    ]


def test_process_identity_rejects_invalid_expected_argv(tmp_path):
    expected = tmp_path / "argv.json"
    expected.write_text("{}", encoding="utf-8")

    with pytest.raises(
        ProcessIdentityError,
        match="non-empty JSON string list",
    ):
        collect_process_identity(
            pid=1,
            expected_executable=Path(sys.executable),
            expected_argv_path=expected,
            attempts=1,
        )
