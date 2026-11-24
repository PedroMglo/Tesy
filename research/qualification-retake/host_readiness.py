"""Check the frozen C281 inputs after relocation, without opening a model runtime."""

import argparse
import hashlib
import json
import mmap
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import c55_inventory as inventory  # noqa: E402
from host_resource_policy import GIB, Q  # noqa: E402
from run_bounded import sha256  # noqa: E402

C281 = ROOT / "results/c281-persistent-r0-runtime-20261005"
FROZEN_SIZE = 63_387_346_208
BLOCK = 4 * 1024**2


def same_file(stat):
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def digest_direct(path, expected_size, expected_digest):
    """Use one aligned, cache-bypassing read pass. Accept the final short read only at EOF."""
    start = time.monotonic()
    h = hashlib.sha256()
    read = 0
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_DIRECT), "rb", buffering=0) as f:
        initial = os.fstat(f.fileno())
        if initial.st_size != expected_size:
            raise ValueError("GGUF size mismatch")
        with mmap.mmap(-1, BLOCK) as block, memoryview(block) as view:
            while read < expected_size:
                n = os.readv(f.fileno(), [view])
                if n != min(BLOCK, expected_size - read):
                    raise ValueError("unexpected GGUF read length")
                h.update(view[:n])
                read += n
        if same_file(initial) != same_file(os.fstat(f.fileno())) or (
            same_file(initial) != same_file(path.stat())
        ):
            raise ValueError("GGUF changed during verification")
    if h.hexdigest() != expected_digest:
        raise ValueError("GGUF digest mismatch")
    return {
        "size_bytes": read,
        "sha256": h.hexdigest(),
        "wall_s": round(time.monotonic() - start, 3),
    }


def memory_window():
    start = time.monotonic()
    samples, stamps = [], []
    while True:
        elapsed = time.monotonic() - start
        stamps.append(elapsed)
        samples.append(inventory.memory()["MemAvailable"])
        if elapsed >= 60:
            break
        time.sleep(max(0, len(stamps) - (time.monotonic() - start)))
    gap = max(b - a for a, b in zip(stamps, stamps[1:], strict=False))
    if len(stamps) < 60 or gap > 1.5:
        raise ValueError("60-second memory inventory incomplete")
    memory = inventory.memory()
    ancestor, _ = inventory.ancestor_headroom(memory["MemTotal"])
    low, high = min(samples), max(samples)
    reserve = max(2 * GIB, high - low + GIB)
    upper = max(0, min(low - reserve, memory["MemTotal"] - reserve, ancestor)) // Q * Q
    return {
        "samples": len(stamps),
        "span_s": round(stamps[-1], 3),
        "max_gap_s": round(gap, 3),
        "mem_available_min": low,
        "mem_available_max": high,
        "reserve_bytes": reserve,
        "cap_upper_bytes": upper,
        "r0_cap_bytes": 20 * GIB,
    }


def dependency_files(protocol, backend, binary):
    # Re-read the frozen files independently of where the dynamic loader would resolve them.
    files = {"binary": (binary, protocol["identity"]["binary_sha256"])}
    for key, digest in protocol["identity"]["library_sha256"].items():
        files["backend/" + Path(key).name] = (backend / key, digest)
    for path, digest in protocol["extra_library_sha256"].items():
        files["system/" + Path(path).name] = (Path(path), digest)
    return {
        key: (
            "ABSENT" if not file.is_file() else "MATCH" if sha256(file) == expected else "MISMATCH"
        )
        for key, (file, expected) in files.items()
    }


def command(*args):
    return subprocess.check_output(args, text=True, timeout=20).strip()


def audit(model, backend, checkout):
    protocol = json.loads((C281 / "protocols/c281-r0-persistent.json").read_text())
    config = json.loads((C281 / "c281-r0-persistent-config.json").read_text())
    binary = Path(config["server_command"][0])
    old = protocol["c120"]["model_stat"]
    stat = model.stat()
    identity_equal = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns) == (
        old["dev"],
        old["ino"],
        old["size"],
        old["mtime_ns"],
    )
    mount = command(
        "findmnt", "--first-only", "-T", str(model.resolve()), "-no", "SOURCE,FSTYPE"
    ).split()
    transport = command("lsblk", "-nrs", "-o", "TRAN", mount[0].split("[")[0]).split()
    # Evaluate the original mount predicate on the real GGUF before any attempt to admit a run.
    try:
        inventory.mounts({"model": model})
        mount_gate = "MATCH"
    except inventory.GateError as exc:
        mount_gate = str(exc)
    window = memory_window()
    head = command("git", "-C", str(backend), "rev-parse", "HEAD")
    files = dependency_files(protocol, backend, binary)
    gpu = command(
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.used,temperature.gpu,driver_version",
        "--format=csv,noheader,nounits",
    )
    frozen_backend = Path("backends/c269-layer-last-use")
    start = datetime.now(UTC).isoformat()
    signal.alarm(300)
    try:
        content = digest_direct(model, FROZEN_SIZE, protocol["identity"]["model_sha256"])
    finally:
        signal.alarm(0)
    return {
        "scope": "INPUT_AUDIT_ONLY",
        "inference": "NOT_RUN",
        "hash_started_utc": start,
        "cpu": inventory.cpu_identity()["model"],
        "gpu_csv": gpu,
        "memory_before_hash": window,
        "model_content": content,
        "model_fs": mount[-1],
        "model_transport": sorted(set(transport)),
        "model_mount_gate": mount_gate,
        "historical_stat_tuple_matches": identity_equal,
        "backend_sha": head,
        "backend_checkout_clean": not command("git", "-C", str(backend), "status", "--porcelain"),
        "main_has_backend_at_launcher_path": (checkout / frozen_backend).is_dir(),
        "frozen_dependency_file_digests": files,
    }


def deadline(*_):
    raise TimeoutError("GGUF verification exceeded 300 s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--backend", type=Path, required=True)
    ap.add_argument("--operational-checkout", type=Path, required=True)
    ap.add_argument("--new-output-dir", type=Path, required=True)
    a = ap.parse_args()
    a.new_output_dir.mkdir()
    signal.signal(signal.SIGALRM, deadline)
    try:
        result = audit(a.model, a.backend, a.operational_checkout)
        pending = a.new_output_dir / ".pending"
        pending.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
        pending.replace(a.new_output_dir / "receipt.json")
    except Exception as exc:
        (a.new_output_dir / "FAIL.txt").write_text(type(exc).__name__ + ": " + str(exc) + "\n")
        raise
