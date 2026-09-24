import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import tesy.process_identity as process_identity_module
from tesy.process_identity import (
    ProcessIdentityError,
    collect_process_identity,
)


def _write_argv(path: Path, argv: list[str]) -> None:
    path.write_text(json.dumps(argv), encoding="utf-8")


def test_process_identity_binds_live_executable_and_argv(tmp_path):
    command = [
        "/bin/sleep",
        "2",
    ]
    expected = tmp_path / "argv.json"
    _write_argv(expected, command)

    process = subprocess.Popen(command)
    try:
        result = collect_process_identity(
            pid=process.pid,
            expected_executable=Path(command[0]),
            expected_argv_path=expected,
        )
    finally:
        process.terminate()
        process.wait(timeout=5)

    assert result["status"] == "PASS"
    assert result["argv"]["status"] == "PASS"
    assert result["executable"]["sha256"]


def test_process_identity_retries_transient_empty_cmdline(
    tmp_path,
    monkeypatch,
):
    command = [
        "/bin/sleep",
        "2",
    ]
    expected = tmp_path / "argv.json"
    _write_argv(expected, command)

    original = process_identity_module._proc_argv
    calls = 0

    def transient_empty(pid: int) -> list[str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ProcessIdentityError("empty process cmdline")
        return original(pid)

    monkeypatch.setattr(
        process_identity_module,
        "_proc_argv",
        transient_empty,
    )

    process = subprocess.Popen(command)
    try:
        result = collect_process_identity(
            pid=process.pid,
            expected_executable=Path(command[0]),
            expected_argv_path=expected,
        )
    finally:
        process.terminate()
        process.wait(timeout=5)

    assert calls >= 2
    assert result["status"] == "PASS"
    assert result["argv"]["status"] == "PASS"


def test_process_identity_reports_exact_argv_mismatch(tmp_path):
    command = [
        "/bin/sleep",
        "2",
    ]
    expected = tmp_path / "argv.json"
    _write_argv(expected, [*command, "unexpected"])

    process = subprocess.Popen(command)
    try:
        result = collect_process_identity(
            pid=process.pid,
            expected_executable=Path(command[0]),
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


def test_process_identity_does_not_retry_invalid_cmdline(
    tmp_path,
    monkeypatch,
):
    expected = tmp_path / "argv.json"
    _write_argv(expected, [sys.executable, "-c", "pass"])

    calls = 0

    def invalid_cmdline(pid: int) -> list[str]:
        nonlocal calls
        calls += 1
        raise ProcessIdentityError("invalid process cmdline")

    monkeypatch.setattr(
        process_identity_module,
        "_proc_argv",
        invalid_cmdline,
    )

    with pytest.raises(
        ProcessIdentityError,
        match="invalid process cmdline",
    ):
        collect_process_identity(
            pid=os.getpid(),
            expected_executable=Path(sys.executable),
            expected_argv_path=expected,
            attempts=5,
            sleep_seconds=0.0,
        )

    assert calls == 1
