"""One ordered R/O/P client block, with a clean process and private files per arm."""

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
ORDERS = ("R", "O", "P")
READY = "PASS_ROP_PREFLIGHT"
DONE = "PASS_C281_TRANSPORT_BLOCK"


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def save(path, row):
    with path.open("x") as f:
        json.dump(row, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")


def version(*args):
    return subprocess.check_output(
        ["git", "-C", str(ROOT), "-c", "core.preloadIndex=false", "-c", "index.threads=1", *args],
        text=True,
    ).strip()


def arguments():
    p = argparse.ArgumentParser(description=__doc__)
    for path in (
        "repo",
        "placement",
        "window",
        "preflight-dir",
        "history-dir",
        "c270",
        "closure-dir",
        "derived-dir",
        "constructor-receipt",
        "c292-receipt",
        "new-output-dir",
    ):
        p.add_argument("--" + path, type=Path, required=True)
    for field in ("commit", "unit-prefix", "preflight-sha256", "window-sha256", "c270-sha256"):
        p.add_argument("--" + field, required=True)
    p.add_argument("--prepared", type=Path)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--arm", choices=ORDERS, help=argparse.SUPPRESS)
    return p.parse_args()


def identity(a):
    need(a.repo.resolve() == ROOT and version("rev-parse", "HEAD") == a.commit, "checkout")
    need(not version("status", "--porcelain"), "dirty checkout")
    need(re.fullmatch(r"tesy-c281-nvme-[a-z0-9-]+", a.unit_prefix), "family unit")
    return dict(
        commit=a.commit,
        tree=version("rev-parse", "HEAD^{tree}"),
        protocol=sha(HERE / "protocol.md"),
        supervisor={f: sha(HERE / f) for f in ("family.py", "transport_profile.py", "review.py")},
        unit_prefix=a.unit_prefix,
        window=a.window_sha256,
        c270=a.c270_sha256,
        c269_preflight=a.preflight_sha256,
        inputs={
            k: str(getattr(a, k).resolve(strict=True))
            for k in (
                "repo",
                "window",
                "placement",
                "c270",
                "preflight_dir",
                "history_dir",
                "closure_dir",
                "derived_dir",
                "constructor_receipt",
                "c292_receipt",
            )
        },
    )


def single(a, out):
    mode = a.arm
    a.unit = a.unit_prefix + "-" + mode.lower()
    profile = run_path(HERE / "transport_profile.py")
    if not a.execute:
        return {
            "status": "PREPARED_ONLY",
            "mode": mode,
            "profile": profile["prepare_arm"](a, out, mode),
        }
    native = profile["run_arm"](a, out, mode)
    save(out / "receipt.json", native)
    grade = run_path(HERE / "review.py")["grade_arm"](out, native, a.history_dir)
    return {
        "status": "PASS_ONE_NATURAL_ARM",
        "mode": mode,
        "grade": grade,
        "receipt_sha256": sha(out / "receipt.json"),
    }


def call_child(a, out, mode, timeout):
    args = list(sys.argv[1:])
    index = args.index("--new-output-dir")
    args[index + 1] = str(out / mode)
    with (out / (mode + ".log")).open("xb") as log:
        with subprocess.Popen(
            [sys.executable, "-IB", str(HERE / "family.py"), *args, "--arm", mode],
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        ) as proc:
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.send_signal(signal.SIGINT)
                try:
                    proc.wait(timeout=35)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                raise TimeoutError(mode + " exceeded its scope deadline") from None
    need(code == 0, mode + " did not finish; see its arm.json and log")
    path = out / mode / "arm.json"
    row = json.loads(path.read_bytes())
    need(
        row["mode"] == mode
        and row["status"] == ("PASS_ONE_NATURAL_ARM" if a.execute else "PREPARED_ONLY"),
        "arm status",
    )
    return dict(sha256=sha(path), arm=row)


def family(a, out, current):
    start = time.monotonic()
    if a.execute:
        need(a.prepared is not None, "static preflight required")
        data = json.loads(a.prepared.read_bytes())
        need(data["status"] == READY and data["identity"] == current, "changed preflight")
        for mode in ORDERS:
            need(
                sha(a.prepared.parent / mode / "arm.json") == data["arms"][mode]["sha256"],
                "preflight arm changed",
            )
    arms = {}
    for mode in ORDERS:
        remaining = 1950 - (time.monotonic() - start)
        need(remaining > 0, "family deadline")
        arms[mode] = call_child(a, out, mode, min(650, remaining))
        need(
            sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) <= 192 * 2**20,
            "family output budget",
        )
    return dict(
        status=DONE if a.execute else READY,
        arms=arms,
        identity=current,
        family_elapsed_s=time.monotonic() - start,
        preflight_sha256=sha(a.prepared) if a.execute else None,
    )


def main():
    a = arguments()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    name = "arm.json" if a.arm else "family.json"
    try:
        current = identity(a)
        result = single(a, out) if a.arm else family(a, out, current)
    except Exception as exc:
        result = dict(
            status="FAIL_PRESERVED",
            mode=a.arm,
            commit=a.commit,
            reason=f"{type(exc).__name__}: {exc}",
        )
    save(out / name, result)
    print(result["status"], result.get("reason", ""), flush=True)
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
