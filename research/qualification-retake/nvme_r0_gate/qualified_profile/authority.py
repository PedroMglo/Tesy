"""Read-only C270/C281 loader controls for a previously authenticated environment."""

import ctypes
import hashlib
import importlib.util
import json
import mmap
import re
import subprocess
from pathlib import Path

P = Path("research/qualification-retake/nvme_r0_gate/driver_pair")
R02 = "8895db5086b272a6aadb31f2cb277c187dd9734f559836f5773691175c01ac4e"
ORIGIN = "0d2b2ad1503c15bb5829ec96d5e6c55b307d5545fd4fe39537607b8e8f5bae44"


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def identity(path):
    st = Path(path).stat()
    return dict(
        dev=st.st_dev,
        ino=st.st_ino,
        size=st.st_size,
        mtime_ns=st.st_mtime_ns,
        ctime_ns=st.st_ctime_ns,
    )


def aliases(folder, expected):
    need(set(p.name for p in folder.iterdir()) == set(expected), "unexpected alias inventory")
    for name, target in expected.items():
        alias = folder / name
        need(
            alias.is_symlink() and str(alias.resolve(strict=True)) == target,
            "foreign provider: " + name,
        )


def mapping_key(fields):
    return tuple(int(v, 16) for v in fields[3].split(":")) + (int(fields[4]),)


def reference_key(path, record):
    # Btrfs can expose different st_dev and VMA device numbers for the same file.
    with (
        Path(path).open("rb") as f,
        mmap.mmap(f.fileno(), mmap.PAGESIZE, access=mmap.ACCESS_COPY) as page,
    ):
        address = ctypes.addressof(ctypes.c_char.from_buffer(page))
        for line in Path("/proc/self/maps").read_text().splitlines():
            fields = line.split(maxsplit=5)
            lo, hi = (int(v, 16) for v in fields[0].split("-"))
            if lo <= address < hi:
                need(
                    len(fields) == 6 and fields[5] == path and int(fields[4]) == record["ino"],
                    "reference VMA",
                )
                return mapping_key(fields)
    raise ValueError("missing passive VMA")


def check_maps(text, allowed, keys):
    mapped = set()
    for line in text.splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) < 6:
            continue
        name = fields[5]
        basename = Path(name.removesuffix(" (deleted)")).name
        if not name.startswith("/") or not (".so." in basename or basename.endswith(".so")):
            continue
        need(not name.endswith(" (deleted)"), "unlinked shared object")
        resolved = str(Path(name).resolve(strict=True))
        need(
            resolved in allowed and mapping_key(fields) == keys[resolved],
            "unexpected mapped ELF: " + basename,
        )
        mapped.add(resolved)
    return mapped


class Authority:
    def __init__(self, repo, preflight_dir, receipt_sha256, arm):
        self.repo = Path(repo)
        folder = Path(preflight_dir)
        chk = folder / "receipt.json"
        need(arm in ("C270", "C281") and sha(chk) == receipt_sha256, "preflight receipt pin")
        self.receipt_sha256 = receipt_sha256
        self.pre = read(chk)
        source = self.repo / P
        self.static = module(source / "server_startup/screen.py", "qualified_static_authority")
        self.origin = module(source / "driver_origin.py", "qualified_driver_origin")
        self.loader = module(source / "profile.py", "qualified_loader_identity")
        self.static.locks(self.repo)
        require_hashes = {
            source / "server_startup/screen.py": self.pre["source_sha256"],
            source / "server_startup/protocol.md": self.pre["protocol_sha256"],
            source / "driver_origin.json": ORIGIN,
            source / "mixed-r02.json": R02,
            folder / "static-map.json": self.pre["static_map_sha256"],
        }
        for path, digest in require_hashes.items():
            need(sha(path) == digest, "preflight chain: " + path.name)
        self.driver = read(source / "driver_origin.json")
        need(
            self.pre["r02_sha256"] == R02
            and self.pre["status"] == "PASS_STATIC_C270_C281_DRIVER_SELECTION"
            and self.pre["deployment_commit"] == self.origin.COMMIT
            and self.origin.deployment() == self.driver["deployment"]
            and self.pre["kernel"] == self.driver["kernel"],
            "signed deployment and static preflight",
        )
        data = read(folder / "static-map.json")
        self.data = data
        self.files = data["files"]
        self.arm = data["arms"][arm]
        self.exe = Path(self.arm["executable"]).resolve(strict=True)
        self.native_search = ":".join(self.arm["native_search"])
        self.monitor_dir = Path(data["monitor_dir"])
        self.links = self.arm["links"]
        self.drivers = {n: Path(p) for n, p in data["driver_aliases"].items()}
        self.initial = {v[1] for v in self.links.values()}
        self.allowed = self.initial | set(map(str, self.drivers.values()))
        need(
            self.pre["arms"][arm]["executable_sha256"]
            == self.arm["executable_sha256"]
            == self.files[str(self.exe)]["sha256"],
            "executable",
        )
        need(
            set(self.drivers) == set(self.origin.ORDER)
            and set(data["monitor_aliases"]) == {self.origin.MON},
            "separate providers",
        )
        need(
            str(self.monitor_dir) not in self.arm["native_search"]
            and self.monitor_dir != Path(data["driver_dir"]),
            "monitor leaks to child",
        )
        for n, p in (data["driver_aliases"] | data["monitor_aliases"]).items():
            need(
                str((self.origin.LIB / n).resolve(strict=True)) == p
                and self.driver["providers"][n]["sha256"] == self.files[p]["sha256"],
                "driver origin: " + n,
            )
        self.recheck()
        text = self.static.command(
            [self.static.LOADER, "--list", self.exe],
            self.static.environment(self.arm["native_search"]),
        )
        now = {
            n: [str(p), str(p.resolve(strict=True))] for n, p in self.static.interpret(text).items()
        }
        need(now == self.links, "preflight no longer selects the same startup objects")
        self.vma_keys = {p: reference_key(p, self.files[p]) for p in self.allowed}

    def recheck(self):
        need(self.origin.kernel() == self.pre["kernel"], "loaded kernel changed")
        aliases(Path(self.data["driver_dir"]), self.data["driver_aliases"])
        aliases(self.monitor_dir, self.data["monitor_aliases"])
        for k, record in self.files.items():
            observed = identity(k)
            need(
                all(record[n] == v for n, v in observed.items()),
                "authenticated file changed: " + Path(k).name,
            )
        for literal, resolved in self.links.values():
            need(str(Path(literal).resolve(strict=True)) == resolved, "startup alias changed")
        for name in self.drivers:
            self.static.first_alias(
                name,
                list(map(Path, self.arm["native_search"])),
                Path(self.data["driver_dir"]) / name,
            )

    def child_env(self, log_prefix):
        return {
            "LD_LIBRARY_PATH": self.native_search,
            "LD_DEBUG": "libs",
            "LD_DEBUG_OUTPUT": str(Path(log_prefix).absolute()),
        }

    def monitor_proof(self):
        self.recheck()
        cli = Path("/usr/bin/nvidia-smi")
        need(sha(cli) == self.pre["monitor_cli_sha256"], "monitor CLI digest")
        env = dict(self.data["monitor_environment"], LD_DEBUG="libs")
        process = subprocess.run(
            [str(cli), "--query-gpu=pci.bus_id,driver_version", "--format=csv,noheader,nounits"],
            env=env,
            capture_output=True,
            timeout=10,
            check=True,
        )
        lines = process.stderr.decode().splitlines()
        loaded = {
            str(Path(z.split("calling init:")[1].strip()).resolve(strict=True))
            for z in lines
            if "calling init:" in z and "libnvidia-ml" in z
        }
        need(loaded == set(self.data["monitor_aliases"].values()), "active monitor provider")
        result = process.stdout.decode().strip().lower().split(", ")
        need(result == ["00000000:c4:00.0", self.pre["kernel"]["release"]], "active monitor device")
        return {
            "nvml_sha256": self.pre["nvml_sha256"],
            "monitor_cli_sha256": self.pre["monitor_cli_sha256"],
            "driver": result[1],
        }

    def live(self, pid):
        base = Path("/proc") / str(pid)
        need((base / "exe").resolve(strict=True) == self.exe, "live executable mismatch")
        return check_maps((base / "maps").read_text(), self.allowed, self.vma_keys)

    def audit(self, log_prefix, pid):
        self.recheck()
        prefix = Path(log_prefix)
        path = prefix.parent / (prefix.name + "." + str(pid))
        need(set(prefix.parent.glob(prefix.name + ".*")) == {path}, "loader journal cardinality")
        need(0 < path.stat().st_size <= 8 << 20, "loader journal limit")
        text = path.read_text()
        loaded = self.loader.initialized(text, pid)
        requested = self.origin.all_requests(text, pid)
        # A native PID must own every directive, including lookups not represented by calling init.
        for line in text.splitlines():
            if line.strip():
                match = re.match(r"\s*(\d+):", line)
                need(match is not None and int(match[1]) == pid, "foreign loader journal PID")
        authorized = set(self.links) | set(self.drivers) | {self.origin.ABSENT}
        need(
            requested <= authorized,
            "unrecognized late library request: " + ",".join(sorted(requested - authorized)),
        )
        need(loaded <= self.allowed, "unrecognized library initializer")
        self.loader.required_present(loaded, self.initial)
        report = self.origin.validate_driver_log(
            self.origin.requests(text, pid), loaded, self.drivers
        )
        return {
            "loader_sha256": sha(path),
            "native_pid": pid,
            "initialized_sha256": {Path(p).name: self.files[p]["sha256"] for p in sorted(loaded)},
            "all_search_names": sorted(requested),
            "driver_providers": report,
            "preflight_sha256": self.receipt_sha256,
        }
