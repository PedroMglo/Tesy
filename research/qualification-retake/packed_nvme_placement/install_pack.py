"""Stage and independently authenticate the original C290 store on local NVMe."""

import argparse
import ctypes
import fcntl
import hashlib
import json
import mmap
import os
import re
import shutil
import stat
import subprocess
import threading
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
QUAL = HERE.parent
ROOT = QUAL.parents[1]
SIZE = 61_096_329_216
DIGEST = "f17e9fbf6f6aed1ad60ca7da3431c5156a946d2e0bf119722afc1f934cbc6b11"
MANIFEST = "4ff6825ccf8d18498c1f2323fd44eacd57c3a8d3278e3aab3adb973a409dd48b"
INDEX = "f8961dcdaa58aa7774e63150b76d69add0dd080181493838528c8f36de543a57"
READBACK = "54273ebffab1294357932b5c4ee6823be7cb9d9d7420b5582b7294c744b658a0"
READBACK_ANALYSIS = "21e52d09ee51078cccd53a506bfa5d2f65273a6ceca3c46828f17dc2a0265d36"
METHOD = "e5638dd00e118ddaf8480c4258cfa8ba5c4b0dfcceb7af04543311e712bc6fac"
RESERVE = 32 * 2**30
BLOCK = 8 * 2**20
SYNC_WINDOW = 128 * 2**20
LIMIT = 1800
CLOCK = time.monotonic
FLAGS = os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECT


def need(test, reason):
    if not test:
        raise ValueError(reason)


def identity(st):
    return dict(
        dev=st.st_dev,
        ino=st.st_ino,
        size=st.st_size,
        mtime_ns=st.st_mtime_ns,
        ctime_ns=st.st_ctime_ns,
    )


def open_direct(path, flags, *, dir_fd=None):
    fd = os.open(path, FLAGS | flags, 0o600, dir_fd=dir_fd)
    try:
        need(
            stat.S_ISREG(os.fstat(fd).st_mode) and fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_DIRECT,
            "regular O_DIRECT FD required",
        )
    except Exception:
        os.close(fd)
        raise
    return fd


def rename_new(dirfd, old, new):
    fn = ctypes.CDLL(None, use_errno=True).renameat2
    fn.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    fn.restype = ctypes.c_int
    if fn(dirfd, os.fsencode(old), dirfd, os.fsencode(new), 1) != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))


def transfer(src, dest, dirfd, unit, size, digest, result, guard, block=BLOCK):
    directory = dest.parent
    partial = f".{dest.name}.{unit}.partial"
    result.update(
        source=str(src),
        destination=str(dest),
        staging_name=partial,
        source_read_bytes=0,
        destination_write_bytes=0,
        destination_reread_bytes=0,
    )
    need(
        not os.path.lexists(dest) and not os.path.lexists(directory / partial),
        "destination or staging already exists",
    )
    with ExitStack() as stack:
        infd = open_direct(src, os.O_RDONLY)
        stack.callback(os.close, infd)
        orig = identity(os.fstat(infd))
        need(
            orig == identity(src.stat()) and orig["size"] == size and size > 0 and size % 4096 == 0,
            "source stat or alignment",
        )
        result["source_stat"] = orig
        buf = stack.enter_context(mmap.mmap(-1, block))
        view = stack.enter_context(memoryview(buf))
        started = CLOCK()
        writefd = open_direct(partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY, dir_fd=dirfd)
        source_hash = hashlib.sha256()
        try:
            for offset in range(0, size, block):
                guard()
                n = min(block, size - offset)
                v = view[:n]
                try:
                    actual = os.preadv(infd, [v], offset)
                    result["source_read_bytes"] += actual
                    need(actual == n, "short source read")
                    source_hash.update(v)
                    actual = os.pwritev(writefd, [v], offset)
                    result["destination_write_bytes"] += actual
                    need(actual == n, "short staging write")
                finally:
                    v.release()
                if (offset + n) % SYNC_WINDOW == 0:
                    os.fdatasync(writefd)
                    os.posix_fadvise(
                        writefd, offset + n - SYNC_WINDOW, SYNC_WINDOW, os.POSIX_FADV_DONTNEED
                    )
            os.fchmod(writefd, 0o444)
            os.fsync(writefd)
            stage_id = identity(os.fstat(writefd))
            need(
                stage_id == identity(os.stat(partial, dir_fd=dirfd, follow_symlinks=False))
                and stage_id["size"] == size,
                "staging writer identity",
            )
        finally:
            os.close(writefd)
        result.update(source_sha256=source_hash.hexdigest(), copy_s=CLOCK() - started)
        need(
            result["source_sha256"] == digest
            and identity(os.fstat(infd)) == orig == identity(src.stat()),
            "source digest or stat changed",
        )
        guard()
        os.fsync(dirfd)
        started = CLOCK()
        verify = open_direct(partial, os.O_RDONLY, dir_fd=dirfd)
        stack.callback(os.close, verify)
        need(identity(os.fstat(verify)) == stage_id, "independent reader identity")
        h = hashlib.sha256()
        for offset in range(0, size, block):
            guard()
            n = min(block, size - offset)
            v = view[:n]
            try:
                actual = os.preadv(verify, [v], offset)
                result["destination_reread_bytes"] += actual
                need(actual == n, "short destination read")
                h.update(v)
            finally:
                v.release()
        result.update(destination_sha256=h.hexdigest(), reread_s=CLOCK() - started)
        need(
            h.hexdigest() == digest
            and stage_id
            == identity(os.fstat(verify))
            == identity(os.stat(partial, dir_fd=dirfd, follow_symlinks=False))
            and orig == identity(os.fstat(infd)) == identity(src.stat()),
            "destination digest or FD identity",
        )
        guard()
        rename_new(dirfd, partial, dest.name)
        os.fsync(dirfd)
        final = identity(os.fstat(verify))
        need(
            final == identity(dest.stat())
            and all(final[k] == stage_id[k] for k in ("dev", "ino", "size", "mtime_ns"))
            and not dest.stat().st_mode & 0o222
            and orig == identity(src.stat()),
            "published FD/path identity",
        )
        result.update(destination_stat=final, size_bytes=size)


def authorities(a, load, target):
    """Validate four small metadata authorities without reading the pack or model."""
    m = load(a.runtime_manifest, MANIFEST)
    idx = load(a.index, INDEX)
    rb = load(a.readback, READBACK)
    summary_path = Path(m["full_readback_result"])
    summary = load(summary_path, READBACK_ANALYSIS)
    need(
        m["schema"] == "tesy-integral-expert-store-runtime-v1"
        and m["index_sha256"] == INDEX
        and m["full_readback_sha256"] == READBACK_ANALYSIS
        and summary["status"] == "PASS_INTEGRAL_STORE_BYTES"
        and summary["index_sha256"] == INDEX
        and m["canonical_model_sha256"] == idx["model_sha256_previous_verified"] == target
        and idx["store_scope"] == "INTEGRAL_GPT_OSS120B_36x128"
        and len(idx["experts"]) == 4608
        and idx["schema"] == "tesy-expert-local-integral-store-v1"
        and rb["source_fd_direct"] is True
        and rb["pack_fd_direct"] is True
        and rb["logical_bytes"] == idx["logical_bytes"] == 61_073_326_080
        and m["pack_sha256_write_stream"]
        == idx["pack_sha256_write_stream"]
        == summary["pack_sha256_write_stream"]
        == rb["pack_sha256_write_stream"]
        == DIGEST
        and rb["status"] == "PASS_FULL_CANONICAL_PACK_READBACK"
        and rb["component_checks"] == summary["component_count"] == m["component_count"] == 27648
        and rb["pack_identity"]["size_bytes"] == m["pack_bytes"] == idx["pack_bytes"] == SIZE,
        "original C290 authorities",
    )
    src = a.source.resolve(strict=True)
    need(
        a.index.samefile(m["index_path"]) and Path(idx["pack_path"]).resolve(strict=True) == src,
        "C290 metadata/source binding",
    )
    return src


def execute(a, out, r):
    cold = run_path(str(QUAL / "phase_fd/integrated/cold_read_fixture/runner.py"))
    io = cold["io"]
    c118 = cold["c135"]
    load = cold["load"]

    def git(*cmd):
        return subprocess.check_output(
            ["git", "-C", str(ROOT), *cmd], text=True, timeout=10
        ).strip()

    need(
        git("rev-parse", "HEAD") == a.commit
        and not git("status", "--porcelain")
        and io.sha256(HERE / "protocol.md") == METHOD,
        "clean frozen Tesy tree",
    )
    r.update(
        commit=a.commit,
        tree=git("rev-parse", "HEAD^{tree}"),
        unit=a.unit,
        program_sha256=io.sha256(Path(__file__)),
        protocol_sha256=METHOD,
        binary_launches=0,
        source_transport="usb",
        destination_transport="nvme",
        index_sha256=INDEX,
        runtime_manifest_sha256=MANIFEST,
        readback_sha256=READBACK,
        readback_analysis_sha256=READBACK_ANALYSIS,
    )
    start = CLOCK()
    src = authorities(a, load, io.TARGET)
    parent = a.destination.parent.resolve(strict=True)
    dest = parent / a.destination.name
    require_name = r"[A-Za-z0-9_.-]{1,100}"
    need(
        re.fullmatch(require_name, a.unit) and re.fullmatch(r"tesy-[A-Za-z0-9_-]+\.bin", dest.name),
        "canonical pack, metadata and destination names",
    )
    c55 = load(a.c55, a.c55_sha256)
    policy = load(a.c55.with_name("resource-policy.json"), c55["canonical_policy_sha256"])
    placement = load(a.placement, io.PLACEMENT_SHA)
    model = Path(placement["working_copy"]).resolve(strict=True)
    need(
        placement["source_sha256"] == placement["destination_direct_reread"]["sha256"] == io.TARGET
        and parent == model.parent
        and c55["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not c55["reason"]
        and c55["selected_stat"] == io.stat_id(model)
        and policy == io.derive_policy(snapshot=policy["snapshot"])
        and io.operational_session_ready(policy)[0],
        "model placement and C55",
    )

    def age():
        return (
            datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])
        ).total_seconds()

    usb = io.disk(src, "usb")
    nvme = io.disk(parent, "nvme")
    need(
        usb != nvme
        and io.mount(src)[1] == "ext4"
        and io.mount(parent)[1] == "btrfs"
        and 0 <= age() < 3400,
        "transports, FS or C55 age",
    )
    io.CAP, io.STOPS = 2**30, 896 * 2**20
    io.scope()
    need(io.cgroup_state()["path"].endswith("/" + a.unit + ".scope"), "scope identity")
    profile = run_path(str(QUAL / "packed_layer_service/profile.py"))
    provider, unchanged = profile["monitor_provider"](SimpleNamespace(token=io.stat_id))
    (out / "raw").mkdir()
    r.update(
        c55_sha256=a.c55_sha256,
        placement_sha256=io.PLACEMENT_SHA,
        monitor_provider=provider,
        source_device=usb.parent.name,
        destination_device=nvme.parent.name,
        free_before_bytes=shutil.disk_usage(parent).free,
        scope_cap_bytes=io.CAP,
        stop_bytes=io.STOPS,
    )
    need(r["free_before_bytes"] >= SIZE + RESERVE, "insufficient NVMe space before C118")
    with ExitStack() as stack:
        directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        stack.callback(os.close, directory)
        fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
        need(
            not os.path.lexists(dest)
            and not os.path.lexists(parent / f".{dest.name}.{a.unit}.partial"),
            "existing output",
        )
        kw = dict(policy=policy, cap_bytes=io.CAP, expected_power=c118.POWER)
        inv = c118.collect(out, a.unit, **kw, sample=lambda: io.monitor(policy)["observation"])
        c118.require_inventory(out, a.unit, inv, **kw)
        io.save(out / "inventory.json", inv)
        r["inventory_sha256"] = io.sha256(out / "inventory.json")
        need(
            age() < 3600 and shutil.disk_usage(parent).free >= SIZE + RESERVE, "admission at start"
        )
        before = {p.parent.name: io.diskstats(p) for p in (usb, nvme)}
        log = stack.enter_context((out / "raw/transfer.jsonl").open("x"))
        stop = threading.Event()
        errors = []
        stats = {
            "samples": 0,
            "minimum_free_bytes": r["free_before_bytes"],
            "max_memory_peak_bytes": 0,
        }

        def sample():
            block = io.monitor(policy)
            free = shutil.disk_usage(parent).free
            need(free >= RESERVE and CLOCK() - start < LIMIT, "disk reserve or elapsed-time limit")
            stats["samples"] += 1
            stats["minimum_free_bytes"] = min(stats["minimum_free_bytes"], free)
            stats["max_memory_peak_bytes"] = max(
                stats["max_memory_peak_bytes"], block["peak_bytes"]
            )
            cold["append_row"](log, dict(free_bytes=free, **block))
            need(log.tell() <= 16 * 2**20, "telemetry budget")

        def watch():
            last = CLOCK()
            try:
                while not stop.wait(0.65):
                    sample()
                    now = CLOCK()
                    need(now - last < 5, "monitor gap")
                    last = now
            except Exception as exc:
                errors.append(exc)

        def guard():
            if errors:
                raise errors[0]
            need(CLOCK() - start < LIMIT, "transfer timeout")

        sample()
        th = threading.Thread(target=watch, daemon=True)
        th.start()
        try:
            transfer(src, dest, directory, a.unit, SIZE, DIGEST, r, guard)
        finally:
            stop.set()
            th.join(timeout=6)
            need(not th.is_alive(), "monitor termination")
            r.update(telemetry=stats, monitor_sha256=io.sha256(out / "raw/transfer.jsonl"))
        guard()
        sample()
        unchanged()
        after = {p.parent.name: io.diskstats(p) for p in (usb, nvme)}
        r.update(
            monitor_sha256=io.sha256(out / "raw/transfer.jsonl"),
            global_diskstats_before=before,
            global_diskstats_after=after,
            free_after_bytes=shutil.disk_usage(parent).free,
            cgroup_final=io.cgroup_state(),
            elapsed_s=CLOCK() - start,
        )
    r["status"] = "PASS_NVME_C290_FULL_PACK_PLACEMENT"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for n in (
        "source",
        "destination",
        "runtime-manifest",
        "index",
        "readback",
        "placement",
        "c55",
        "new-output-dir",
    ):
        parser.add_argument("--" + n, type=Path, required=True)
    for n in ("unit", "commit", "c55-sha256"):
        parser.add_argument("--" + n, required=True)
    a = parser.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir(mode=0o700)
    r = {"status": "FAIL_PRESERVED"}
    try:
        execute(a, out, r)
    except Exception as exc:
        r["reason"] = f"{type(exc).__name__}: {exc}"
    with (out / "receipt.json").open("x") as f:
        json.dump(r, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(r["status"])
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
