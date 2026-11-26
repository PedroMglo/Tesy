"""Inspect live C270/C281 startup providers on private FIFOs without model inference."""

import argparse
import errno
import json
import os
import subprocess
import time
from pathlib import Path

from linkage import (
    HERE,
    PROTOCOL,
    REPO,
    LibraryAuthority,
    child_ldd,
    need,
    numeric_census,
    run_bounded,
    sha,
)


def save(path, obj):
    with path.open("x") as f:
        json.dump(obj, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")


def held_writer(fifo, child):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        need(child.poll() is None, "child exited before input gate")
        try:
            return os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        except OSError as exc:
            if exc.errno != errno.ENXIO:
                raise
            time.sleep(0.01)
    raise ValueError("input gate not reached")


def waiting_on_fifo(pid, fifo):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        names = []
        for link in Path(f"/proc/{pid}/fd").iterdir():
            try:
                names.append(os.readlink(link))
            except FileNotFoundError:
                continue
        need(not any(".gguf" in s for s in names), "unexpected model descriptor")
        if str(fifo) in names:
            return
        time.sleep(0.01)
    raise ValueError("no live reader for the private input FIFO")


def on_fifo(a, out, arm, mode):
    folder = out / (arm + "-" + mode)
    folder.mkdir()
    expected = LibraryAuthority(
        a.preflight_dir,
        a.preflight_sha256,
        a.build_dir,
        a.build_sha256,
        arm,
        "gold" if mode == "gold" else "candidate",
    )
    prefix = folder / "loader"
    fifo = folder / "input.pipe"
    os.mkfifo(fifo, 0o600)
    opts = (
        [str(folder / "absent-model"), str(fifo), str(folder / "unused-output"), "--ngl", "12"]
        if arm == "C270"
        else ["--grammar-file", str(fifo), "--help"]
    )
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "CUDA_VISIBLE_DEVICES": "",
        "OMP_NUM_THREADS": "1",
        **expected.child_env(prefix),
    }
    if mode == "wrong-original":
        env["LD_LIBRARY_PATH"] = expected.original_search
    with (folder / "stdout").open("xb") as stdout, (folder / "stderr").open("xb") as stderr:
        child = subprocess.Popen([expected.exe, *opts], stdout=stdout, stderr=stderr, env=env)
        try:
            fd = held_writer(fifo, child)
            try:
                pid = child.pid
                need(
                    Path(f"/proc/{pid}/exe").resolve(strict=True) == expected.exe,
                    "owned executable",
                )
                waiting_on_fifo(pid, fifo)
                backend = a.backend.resolve(strict=True)
                census = child_ldd(expected.native_search)(expected.exe, backend)
                mapped = run_bounded.mapped_backend_libraries(pid, backend)
                if mode == "wrong-original":
                    wanted = expected.image
                    old = Path(expected.original_links["libllama.so.0"][1])
                    need(
                        wanted != old
                        and wanted not in {Path(k) for k in mapped}
                        and any((backend / k).resolve(strict=True) == old for k in mapped),
                        "negative really loaded original",
                    )
                    for check in (
                        lambda: expected.live(pid),
                        lambda: numeric_census(census, mapped),
                    ):
                        try:
                            check()
                        except ValueError:
                            pass
                        else:
                            raise ValueError("foreign image accepted")
                    original = child_ldd(expected.original_search)(expected.exe, backend)
                    observed = numeric_census(original, mapped)
                else:
                    need(expected.initial <= expected.live(pid), "missing live startup object")
                    observed = numeric_census(census, mapped)
                    need(
                        str(expected.image) in mapped
                        and mapped[str(expected.image)] == expected.image_sha,
                        "private library excluded from census",
                    )
            finally:
                os.close(fd)
            rc = child.wait(timeout=12)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            fifo.unlink()
    need(rc == (1 if arm == "C270" else 0), "unexpected no-model exit: " + str(rc))
    report = expected.smoke_log(prefix, pid) if mode != "wrong-original" else None
    return dict(
        argv=[str(expected.exe), *opts],
        selected_sha256=expected.image_sha,
        executable_sha256=expected.arm["executable_sha256"],
        native_search=env["LD_LIBRARY_PATH"],
        arm=arm,
        selection=mode,
        loaded_numeric=observed,
        loader=report,
        exit=rc,
        expected_candidate_rejected=mode == "wrong-original",
        journal_sha256=sha(Path(str(prefix) + "." + str(pid))),
        stdout_bytes=(folder / "stdout").stat().st_size,
        stderr_bytes=(folder / "stderr").stat().st_size,
        no_model_fd=True,
        forwards=0,
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for label in ("build-dir", "preflight-dir", "backend", "new-output-dir"):
        ap.add_argument("--" + label, required=True, type=Path)
    for label in ("build-sha256", "preflight-sha256", "measurement-commit"):
        ap.add_argument("--" + label, required=True)
    a = ap.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    started = time.monotonic()
    arms = []
    try:
        need(sha(HERE / "protocol.md") == PROTOCOL, "profile protocol")
        cg = run_bounded.cgroup_state()
        need(cg["memory_max"] == 512 * 2**20 and cg["swap_max"] == 0, "smoke cgroup")

        def git(*args):
            return subprocess.check_output(["git", "-C", REPO, *args], text=True).strip()

        need(
            git("rev-parse", "HEAD") == a.measurement_commit and not git("status", "--porcelain"),
            "clean checkout",
        )
        for arm in ("C270", "C281"):
            for mode in ("gold", "candidate", "wrong-original"):
                arms.append(on_fifo(a, out, arm, mode))
                need(
                    time.monotonic() - started <= 120
                    and sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) <= 16 * 2**20,
                    "startup scope budget",
                )
        result = {"status": "PASS_C270_C281_ONE_PROVIDER_STARTUP"}
    except Exception as exc:
        result = {"status": "FAIL_PRESERVED", "reason": str(exc)}
    result.update(
        arms=arms,
        finished_processes=len(arms),
        model_launches=0,
        elapsed_s=time.monotonic() - started,
        protocol_sha256=PROTOCOL,
        commit=a.measurement_commit,
        cgroup=run_bounded.cgroup_state(),
        build_sha256=a.build_sha256,
        preflight_sha256=a.preflight_sha256,
        source_sha256=sha(HERE / "smoke.py"),
    )
    save(out / "receipt.json", result)
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
