"""Authenticate the loader closure of the historical capture and server without executing either."""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import resource
import signal
import stat
import subprocess
import sys
import time
import types
from pathlib import Path

Q = "research/qualification-retake/"
S = Q + "nvme_r0_gate/driver_pair/"
C270 = "results/c270-last-use-ordered-fidelity-20261004/protocol.json"
C281 = "results/c281-persistent-r0-runtime-20261005/"
PINS = {
    C270: "10ee7ec18d4b7d1d44b80eca7dbc2ff2a48ccebdd83bc2c73dadc26289f6a616",
    C281 + "command.json": "5bf1f256ff97f8ff5b410a511913deb664c9f0a60cfb7554bc12dc75dfb3a77e",
    C281
    + "runtime-manifest.json": "2ae902bb57dd748d882e584b2dd6c7c1f8336ac7c76ce7b31fbe1651bfaf9bfb",
    Q
    + "elf-evidence/receipt.json": "4c72368e6d971c6b228bf323116d6148ff530f5a4ae5e3d80e7ac4abb43772b1",  # noqa: E501
    Q
    + "nvme_r0_gate/inputs/receipt.json": "29795e9d68452efb6e0dea1df9e873b27fcf1011d36b899abd52bfdd91ce2a8e",  # noqa: E501
    S + "mixed-r02.json": "8895db5086b272a6aadb31f2cb277c187dd9734f559836f5773691175c01ac4e",
    S + "driver_origin.json": "0d2b2ad1503c15bb5829ec96d5e6c55b307d5545fd4fe39537607b8e8f5bae44",
    S + "driver_origin.py": "c71f64856df95b11f324201e5ebf4a065850961892c1e064ac498eaefaaafacb",
}
PROTOCOL = "f1ca48478101c78188f35e1e3163607a2e184ae70148c20c14f94894d2d7377a"
SMI = "616dd34c46398fdd01b73eea69bef30d1388698d494a6e2bc187857f38a938ea"
CLEAN = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
LOADER = Path("/lib64/ld-linux-x86-64.so.2")


def check(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, value):
    with path.open("x") as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def command(args, env=None):
    return subprocess.check_output(
        args, env=CLEAN if env is None else env, text=True, timeout=18
    ).strip()


def info(st):
    return dict(
        dev=st.st_dev,
        ino=st.st_ino,
        size=st.st_size,
        mtime_ns=st.st_mtime_ns,
        ctime_ns=st.st_ctime_ns,
    )


class Files:
    def __init__(self):
        self.rows = {}
        self.size = 0

    def require(self, path, want):
        target = path.resolve(strict=True)
        real = str(target)
        current = info(target.stat())
        if real not in self.rows:
            self.size += current["size"]
            check(self.size <= 3 * 2**30, "ELF read budget")
            with target.open("rb") as f:
                st = os.fstat(f.fileno())
                check(stat.S_ISREG(st.st_mode) and info(st) == current, "file replacement")
                actual = hashlib.file_digest(f, "sha256").hexdigest()
                check(info(os.fstat(f.fileno())) == current, "file changed during hashing")
            self.rows[real] = {"sha256": actual, **current}
        row = self.rows[real]
        check(row == {"sha256": want, **current}, "ELF content/identity " + target.name)
        return target


def interpret(text):
    links = {}
    vdso = False
    for line in text.strip().splitlines():
        words = line.split()
        check(words and re.fullmatch(r"\(0x[0-9a-f]+\)", words[-1]), "unresolved loader record")
        if words[:-1] == ["linux-vdso.so.1"]:
            check(not vdso, "duplicate vDSO")
            vdso = True
            continue
        if len(words) == 2 and Path(words[0]).name == LOADER.name:
            name, literal = LOADER.name, words[0]
        else:
            check(len(words) == 4 and words[1] == "=>", "unknown loader record")
            name, literal = words[0], words[2]
        check(
            name == Path(name).name and name not in links and Path(literal).is_absolute(),
            "ambiguous loader record",
        )
        links[name] = Path(literal)
    check(vdso and LOADER.name in links, "missing interpreter or vDSO")
    return links


def environment(dirs):
    return dict(CLEAN, LD_LIBRARY_PATH=":".join(map(str, dirs)))


def first_alias(name, search, alias):
    winner = next((d / name for d in search if os.path.lexists(d / name)), None)
    check(winner == alias and winner.is_symlink(), "foreign first provider " + name)


def locks(repo):
    files = {}
    for key, sha in PINS.items():
        raw = (repo / key).read_bytes()
        check(digest(raw) == sha, "authority changed " + key)
        files[key] = raw if key.endswith(".py") else json.loads(raw)
    return files


def static(repo, out, record):
    check(repo.is_absolute() and out.is_absolute(), "absolute roots required")
    locked = locks(repo)
    origin = types.ModuleType("driver_origin")
    exec(compile(locked[S + "driver_origin.py"], "sealed_driver_origin", "exec"), origin.__dict__)
    origin.cmd = (
        command  # Use the original signed-deployment checks in a clean process environment.
    )
    previous = locked[S + "driver_origin.json"]
    r02 = locked[S + "mixed-r02.json"]
    kernel, deployment = origin.kernel(), origin.deployment()
    check(
        kernel == previous["kernel"] == r02["kernel"] and deployment == previous["deployment"],
        "kernel/deployment",
    )
    check(
        deployment["commit"] == r02["ostree_commit"]
        and r02["status"] == "PASS_C269_MIXED_KERNEL_SINGLE_DRIVER_DEPLOYMENT_ONLY",
        "R02 evidence",
    )
    record.update(kernel=kernel, deployment_commit=deployment["commit"])
    files = Files()
    native, monitor = out / "driver", out / "monitor"
    native.mkdir(mode=0o700)
    monitor.mkdir(mode=0o700)
    aliases = {}
    for name in (*origin.ORDER, origin.MON):
        ref = previous["providers"][name]
        check(
            origin.object_info(name) == {k: v for k, v in ref.items() if k != "sha256"},
            "OSTree provider " + name,
        )
        target = files.require(origin.LIB / name, ref["sha256"])
        if name == origin.MON:
            check(r02["nvml_monitor_sha256"] == ref["sha256"], "monitor identity")
            alias = monitor / name
        else:
            observed = r02["driver_objects"][name]
            check(
                observed["sha256"] == ref["sha256"] and observed["initialized"],
                "native R02 provider",
            )
            alias = native / name
        alias.symlink_to(target)
        aliases[name] = str(target)
    check(not os.path.lexists(origin.LIB / origin.ABSENT), "unexpected optional driver")
    check(
        set(p.name for p in native.iterdir()) == set(origin.ORDER)
        and set(p.name for p in monitor.iterdir()) == {origin.MON},
        "alias sets",
    )
    first_alias(origin.MON, [monitor], monitor / origin.MON)
    files.require(Path("/usr/bin/nvidia-smi"), SMI)
    common = previous["r01_startup"][LOADER.name]["sha256"]
    files.require(LOADER, common)
    inputs = locked[Q + "nvme_r0_gate/inputs/receipt.json"]
    inventory = locked[Q + "elf-evidence/receipt.json"]
    server = locked[C281 + "runtime-manifest.json"]
    proto = locked[C270]
    capture = Path(proto["runs"][0]["command"][0])
    argv = locked[C281 + "command.json"]["monitor_command"]
    serve = Path(argv[argv.index("--") + 1])
    backend = Path(proto["backend_root"])
    builds = (backend / "build-c269-cuda/bin", serve.parent)
    refs = {
        r["load_name"]: (r["resolved_file"], r["resolved_sha256"])
        for r in inventory["selected_frozen_and_unpinned"]
    }
    c270 = {name: pair for name, pair in refs.items() if pair[0] in inputs["startup_dso_sha256"]}
    check(
        len(c270) == 17 and len(refs) == 23 and dict(c270.values()) == inputs["startup_dso_sha256"],
        "historical startup cardinality or digest",
    )
    check(
        inputs["server_sha256"] == server["binary_sha256"] == inventory["executable_sha256"],
        "historical server identity",
    )
    paths = {Path(k).name: (backend / k).resolve(strict=True) for k in server["library_sha256"]}
    paths.update(
        {
            Path(k).name: Path(k).resolve(strict=True)
            for k in server["extra_library_sha256"]
            if Path(k).name.startswith("libmtmd.")
        }
    )
    check(len(paths) == 8, "C269/server source libraries")
    metadata = dict(
        driver_dir=str(native),
        monitor_dir=str(monitor),
        driver_aliases={k: aliases[k] for k in origin.ORDER},
        monitor_aliases={origin.MON: aliases[origin.MON]},
        monitor_environment=environment([monitor]),
        arms={},
    )
    arms = (
        ("C270", capture, inputs["capture_sha256"], c270, [builds[0], native]),
        ("C281", serve, inputs["server_sha256"], refs, [*builds, native]),
    )
    for arm, exe, binary_hash, expected, search in arms:
        binary = files.require(exe, binary_hash)
        for name in origin.ORDER:
            first_alias(name, search, native / name)
        check(
            not any(os.path.lexists(d / origin.ABSENT) for d in search),
            "optional provider in search path",
        )
        listing = command([LOADER, "--list", exe], env=environment(search))
        (out / (arm + ".list")).write_text(listing + "\n")
        links = interpret(listing)
        check(set(links) == set(expected) | {LOADER.name}, "different dependency set " + arm)
        table = {}
        public = {}
        for name, literal in sorted(links.items()):
            basename, sha = (LOADER.name, common) if name == LOADER.name else expected[name]
            target = files.require(literal, sha)
            check(target.name == basename, "different resolved filename " + name)
            if basename in paths:
                check(target == paths[basename], "wrong source library " + basename)
            if name == "libcuda.so.1":
                check(
                    literal == native / name and str(target) == aliases[name],
                    "wrong CUDA selection",
                )
            table[name] = [str(literal), str(target)]
            public[name] = {"file": basename, "sha256": sha}
        metadata["arms"][arm] = dict(
            executable=str(binary),
            executable_sha256=binary_hash,
            native_search=list(map(str, search)),
            links=table,
        )
        record["arms"][arm] = dict(
            executable_sha256=binary_hash,
            named_dependencies=len(expected),
            objects=public,
            kernel_vdso=True,
        )
    for absname, row in files.rows.items():
        check(
            info(Path(absname).stat()) == {k: v for k, v in row.items() if k != "sha256"},
            "ELF changed before close",
        )
    for arm in metadata["arms"].values():
        for literal, target in arm["links"].values():
            check(
                str(Path(literal).resolve(strict=True)) == target,
                "startup selection changed before close",
            )
    for name, target in aliases.items():
        alias = (monitor if name == origin.MON else native) / name
        check(str(alias.resolve(strict=True)) == target, "alias changed before close")
    check(
        origin.kernel() == kernel and origin.deployment() == deployment,
        "kernel/deployment changed before close",
    )
    metadata["files"] = files.rows
    dump(out / "static-map.json", metadata)
    record.update(
        static_map_sha256=digest((out / "static-map.json").read_bytes()),
        distinct_elf_bytes=files.size,
        native_alias_sha256={
            k: files.rows[v]["sha256"] for k, v in aliases.items() if k != origin.MON
        },
        nvml_sha256=files.rows[aliases[origin.MON]]["sha256"],
        monitor_cli_sha256=SMI,
        startup_processes=0,
        inference_calls=0,
        late_lookup_status="NOT_RUN",
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--new-output-dir", required=True, type=Path)
    a = ap.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.absolute()
    out.mkdir(mode=0o700)
    started = time.monotonic()
    record = dict(
        status="FAIL_PRESERVED",
        source_sha256=digest(Path(__file__).read_bytes()),
        protocol_sha256=PROTOCOL,
        r02_sha256=PINS[S + "mixed-r02.json"],
        arms={},
        locks=PINS,
        started_utc=dt.datetime.now(dt.UTC).isoformat(),
    )

    def expire(*_):
        raise TimeoutError("120s limit")

    signal.signal(signal.SIGALRM, expire)
    signal.alarm(120)
    try:
        check(
            digest(Path(__file__).with_name("protocol.md").read_bytes()) == PROTOCOL,
            "protocol changed",
        )
        # Executing from the integrated checkout binds the program and protocol to its clean tree.
        repo = a.repo.resolve(strict=True)
        head = command(
            ["/usr/bin/git", "-C", repo, "rev-parse", "HEAD", "HEAD^{tree}"]
        ).splitlines()
        check(
            len(head) == 2 and not command(["/usr/bin/git", "-C", repo, "status", "--porcelain"]),
            "clean checkout",
        )
        for path in [Path(__file__).resolve(), Path(__file__).resolve().with_name("protocol.md")]:
            rel = path.relative_to(repo)
            check(
                command(["/usr/bin/git", "-C", repo, "ls-files", "--error-unmatch", str(rel)])
                == str(rel),
                "untracked procedure",
            )
        record.update(head=head[0], tree=head[1])
        static(repo, out, record)
        check(
            command(["/usr/bin/git", "-C", repo, "rev-parse", "HEAD"]) == head[0]
            and not command(["/usr/bin/git", "-C", repo, "status", "--porcelain"]),
            "checkout changed during check",
        )
        check(
            sum(p.stat().st_size for p in out.iterdir() if p.is_file()) < 2**21 - 32768,
            "output cap",
        )
        check(
            max(
                resource.getrusage(x).ru_maxrss
                for x in (resource.RUSAGE_SELF, resource.RUSAGE_CHILDREN)
            )
            < 256 * 1024,
            "RSS cap",
        )
        record["status"] = "PASS_STATIC_C270_C281_DRIVER_SELECTION"
    except Exception as exc:
        record["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        signal.alarm(0)
        record["elapsed_s"] = time.monotonic() - started
        record["max_rss_kib"] = {
            k: resource.getrusage(v).ru_maxrss
            for k, v in [("self", resource.RUSAGE_SELF), ("children", resource.RUSAGE_CHILDREN)]
        }
        dump(out / "receipt.json", record)
    print(record["status"])
    return int(record["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    sys.exit(main())
