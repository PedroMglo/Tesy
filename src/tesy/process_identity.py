from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


class ProcessIdentityError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_argv(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, list)
        or not payload
        or any(not isinstance(item, str) or not item for item in payload)
    ):
        raise ProcessIdentityError(
            "expected argv must be a non-empty JSON string list"
        )
    return payload


def _proc_argv(pid: int) -> list[str]:
    raw = (Path("/proc") / str(pid) / "cmdline").read_bytes()
    if not raw:
        raise ProcessIdentityError("empty process cmdline")
    items = raw.split(b"\0")
    if items[-1] == b"":
        items.pop()
    if not items or any(not item for item in items):
        raise ProcessIdentityError("invalid process cmdline")
    try:
        return [item.decode("utf-8", errors="strict") for item in items]
    except UnicodeDecodeError as exc:
        raise ProcessIdentityError(
            "process cmdline is not valid UTF-8"
        ) from exc


def collect_process_identity(
    *,
    pid: int,
    expected_executable: Path,
    expected_argv_path: Path,
    attempts: int = 200,
    sleep_seconds: float = 0.01,
) -> dict[str, Any]:
    if pid <= 0:
        raise ProcessIdentityError("pid must be positive")
    if attempts <= 0:
        raise ProcessIdentityError("attempts must be positive")

    expected_exe = expected_executable.expanduser().resolve(strict=True)
    expected_argv = _load_argv(expected_argv_path)
    proc = Path("/proc") / str(pid)

    last_error: str | None = None
    for _ in range(attempts):
        if not proc.exists():
            raise ProcessIdentityError(
                f"process {pid} exited before identity could be verified"
            )
        try:
            observed_exe = (proc / "exe").resolve(strict=True)
            observed_argv = _proc_argv(pid)
        except OSError as exc:
            last_error = str(exc)
            time.sleep(sleep_seconds)
            continue
        except ProcessIdentityError as exc:
            if str(exc) != "empty process cmdline":
                raise
            last_error = str(exc)
            time.sleep(sleep_seconds)
            continue

        if observed_exe == expected_exe:
            mismatches: list[str] = []
            if observed_argv != expected_argv:
                mismatches.append(
                    "process argv does not exactly match frozen argv"
                )
            return {
                "schema": "tesy.process_identity.v1",
                "classification": "MEASURED_LOCAL_PROVENANCE",
                "status": "PASS" if not mismatches else "FAIL",
                "pid": pid,
                "executable": {
                    "expected": str(expected_exe),
                    "observed": str(observed_exe),
                    "sha256": _sha256(expected_exe),
                },
                "argv": {
                    "expected": expected_argv,
                    "observed": observed_argv,
                    "status": (
                        "PASS"
                        if observed_argv == expected_argv
                        else "FAIL"
                    ),
                },
                "mismatches": mismatches,
                "claim_boundary": (
                    "PASS binds a live process to the expected executable "
                    "bytes and exact argv. It does not establish model "
                    "correctness, backend placement or performance."
                ),
            }

        last_error = (
            f"process executable {observed_exe} != {expected_exe}"
        )
        time.sleep(sleep_seconds)

    raise ProcessIdentityError(
        "timed out waiting for expected executable"
        + (f": {last_error}" if last_error else "")
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--expected-executable", required=True, type=Path)
    parser.add_argument("--expected-argv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to replace {args.output}")

    payload = collect_process_identity(
        pid=args.pid,
        expected_executable=args.expected_executable,
        expected_argv_path=args.expected_argv,
    )
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
