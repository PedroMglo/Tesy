"""Compare the current glibc load-time dependency selection to C281 without a server."""

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from parallel_runtime import parallel_environment

C281 = Path(__file__).resolve().parents[2] / "results/c281-persistent-r0-runtime-20261005"
MANIFEST = "2ae902bb57dd748d882e584b2dd6c7c1f8336ac7c76ce7b31fbe1651bfaf9bfb"
PROTOCOL = "01113b9a5ecc418818a8a26aa5a63e87de699005adb13c3a60748e315d5c6e3d"
CONFIG = "9be7be9c3a4c141c355842b0d42bdcfd0ce775d839f69fc8eff6cc2e2e783148"
LOADER = "/lib64/ld-linux-x86-64.so.2"
CLEAN_ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}


def stable_hash(path):
    def identity(st):
        return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns

    with path.open("rb") as data:
        before = identity(os.fstat(data.fileno()))
        result = hashlib.file_digest(data, "sha256").hexdigest()
        if before != identity(os.fstat(data.fileno())) or before != identity(path.stat()):
            raise ValueError("file changed during digest")
    return result


def pinned(path, checksum):
    if stable_hash(path) != checksum:
        raise ValueError("input digest mismatch")
    return json.loads(path.read_bytes())


def command(*args):
    return subprocess.check_output(args, text=True, env=CLEAN_ENV, timeout=15)


def abi_name(name):
    # The C281 manifest keys identify real files. Driver and libgcc have different real/ABI names.
    if name.startswith("libcuda.so."):
        return "libcuda.so.1"
    if name.startswith("libgcc_s-"):
        return "libgcc_s.so.1"
    match = re.fullmatch(r"(.+\.so\.\d+)(?:\..*)?", name)
    return match[1] if match else name


def selections(output):
    found, auxiliary = {}, []
    for line in output.splitlines():
        if "=>" in line:
            name, resolution = line.split("=>", 1)
            name = name.strip()
            target = resolution.strip().split()[0]
            if name in found or not (target == "not" or target.startswith("/")):
                raise ValueError("unrecognized or duplicate loader entry")
            found[name] = None if target == "not" else Path(target).resolve(strict=True)
        else:
            bare = line.strip().split()[0]
            if bare not in ["linux-vdso.so.1", LOADER]:
                raise ValueError("unrecognized bare loader entry")
            auxiliary.append(Path(bare).name)
    return found, sorted(auxiliary)


def audit():
    mark = time.monotonic()
    manifest = pinned(C281 / "runtime-manifest.json", MANIFEST)
    protocol = pinned(C281 / "protocols/c281-r0-persistent.json", PROTOCOL)
    config = pinned(C281 / "c281-r0-persistent-config.json", CONFIG)
    backend = Path(config["backend_root"]).resolve(strict=True)
    binary = Path(manifest["binary"])
    digest = stable_hash(binary)
    if (
        digest != manifest["binary_sha256"]
        or digest != protocol["identity"]["binary_sha256"]
        or str(binary) != config["server_command"][0]
        or protocol["parallel_runtime"] != manifest["parallel_runtime"]
        or protocol["extra_library_sha256"] != manifest["extra_library_sha256"]
        or protocol["identity"]["library_sha256"] != manifest["library_sha256"]
    ):
        raise ValueError("C281 binary or contract mismatch")
    phdrs = command("/usr/bin/readelf", "-lW", str(binary))
    if re.findall(r"Requesting program interpreter: (.*?)\]", phdrs) != [LOADER]:
        raise ValueError("unexpected program interpreter")
    dynamic = command("/usr/bin/readelf", "-dW", str(binary))
    needed = sorted(re.findall(r"\(NEEDED\).*?\[(.*?)\]", dynamic))
    if not needed:
        raise ValueError("missing dynamic dependency table")
    selected, auxiliary = selections(command("/usr/bin/ldd", str(binary)))
    frozen = {}
    for key in ["library_sha256", "extra_library_sha256"]:
        for path, expected in manifest[key].items():
            name = abi_name(Path(path).name)
            if name in frozen:
                raise ValueError("ambiguous frozen ABI name")
            frozen[name] = (Path(path).name, expected)

    rows, actual_backend = [], {}
    for name in sorted(set(frozen) | set(selected)):
        path = selected.get(name)
        checksum = stable_hash(path) if path else None
        basename, expected = frozen.get(name, (None, None))
        if name not in selected:
            status = "NOT_LISTED"
        elif path is None:
            status = "NOT_FOUND"
        elif expected is None:
            status = "UNPINNED"
        else:
            status = "MATCH" if checksum == expected else "MISMATCH"
        rows.append(
            {
                "load_name": name,
                "frozen_file": basename,
                "frozen_sha256": expected,
                "resolved_file": path.name if path else None,
                "resolved_sha256": checksum,
                "status": status,
            }
        )
        # Use the exact key convention of run_bounded.backend_library_hashes on the same ldd output.
        if path and (path.is_relative_to(backend) or path.name.startswith(("libggml", "libllama"))):
            key = path.relative_to(backend) if path.is_relative_to(backend) else path
            actual_backend[str(key)] = checksum

    counts = {k: sum(r["status"] == k for r in rows) for k in sorted({r["status"] for r in rows})}
    omp = protocol["parallel_runtime"]
    omp_names = {abi_name(Path(p).name): h for p, h in omp["libraries_sha256"].items()}
    omp_selected = {
        r["load_name"]: r["resolved_sha256"]
        for r in rows
        if r["resolved_sha256"] and r["load_name"].startswith(("libgomp", "libomp", "libiomp"))
    }
    env_matches = parallel_environment(os.environ | config["explicit_env"]) == omp["environment"]
    backend_matches = actual_backend == manifest["library_sha256"]
    matches = counts == {"MATCH": len(frozen)} and backend_matches and omp_names == omp_selected
    if stable_hash(binary) != digest:
        raise ValueError("binary changed during inspection")
    return {
        "status": "MATCH" if matches and env_matches else "C281_RUNTIME_IDENTITY_NO_GO",
        "observed_utc": datetime.now(UTC).isoformat(),
        "elapsed_s": round(time.monotonic() - mark, 3),
        "interpreter": Path(LOADER).name,
        "unfrozen_auxiliary": auxiliary,
        "executable_sha256": digest,
        "manifest_sha256": MANIFEST,
        "c281_protocol_sha256": PROTOCOL,
        "c281_config_sha256": CONFIG,
        "direct_needed": needed,
        "selected_frozen_and_unpinned": rows,
        "counts": counts,
        "backend_original_keys_and_digests_match": backend_matches,
        "parallel_library_digest_matches": omp_names == omp_selected,
        "parallel_shell_environment_matches": env_matches,
        "loader_override_names_in_shell": sorted(
            k for k in os.environ if k.startswith("LD_") or k == "GLIBC_TUNABLES"
        ),
        "runtime_mapped_objects": "NOT_RUN",
        "model_forwards": 0,
    }


def deadline(_signal, _frame):
    raise TimeoutError("ELF audit exceeded budget")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new-output-dir", required=True, type=Path)
    out = parser.parse_args().new_output_dir
    out.mkdir()
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(60)
    try:
        result = audit()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        result = {"status": "FAIL", "error_type": type(exc).__name__}
    finally:
        signal.alarm(0)
    with (out / ".pending").open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    (out / ".pending").replace(out / "receipt.json")
    print(result["status"])
    return int(result["status"] == "FAIL")


if __name__ == "__main__":
    raise SystemExit(main())
