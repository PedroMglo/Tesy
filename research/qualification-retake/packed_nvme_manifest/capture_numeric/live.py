"""Authority for the two C292 captures using the static C270 driver selection."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[1]
REPO = QUAL.parents[1]
sys.path.insert(0, str(QUAL / "phase_fd/integrated/profile"))
import linkage  # noqa: E402
from authority import Authority, aliases, identity, reference_key  # noqa: E402

static = linkage.load_module(HERE.parent / "capture_profile/screen.py", "c292_loader_closure")
need, read, sha = linkage.need, linkage.read, linkage.sha
CLOSURE = "7b0ca3bcc778f527dfc4cdfab3aaa3f93687045cba5e12d5a74b8310aeb7b670"
DERIVED = "cd4c0665c5485268cddfc7dba576b1cf490222c120cf34f72d555a6cbccbc5b9"
CONSTRUCTOR = "c81c15cb9614fd2780f35d5f3fc2b96ce280056f9da363ca74b42b112d1642f1"
STORE_ENV = "TESY_EXPERT_STORE_MANIFEST"


def proc_pack(proc, pack, expected):
    """The C291 constructor keeps the same open file description until normal destruction."""
    descriptors = []
    for link in (proc / "fd").iterdir():
        try:
            target = os.readlink(link)
            if target.removesuffix(" (deleted)") != str(pack):
                continue
            actual = static.derive.runtime_stat(link.stat())
            info = (proc / "fdinfo" / link.name).read_text().splitlines()
            flags = [int(r.split()[1], 8) for r in info if r.startswith("flags:")]
            if os.readlink(link) != target:
                continue
        except FileNotFoundError:
            continue
        need(
            target == str(pack)
            and actual == expected
            and len(flags) == 1
            and flags[0] & os.O_DIRECT
            and flags[0] & os.O_ACCMODE == os.O_RDONLY,
            "foreign, deleted, buffered or writable pack descriptor",
        )
        descriptors.append((int(link.name), flags[0]))
    need(len(descriptors) <= 1, "unexpected duplicate open pack descriptor")
    return descriptors


class CaptureAuthority(Authority):
    def __init__(self, a, mode):
        super().__init__(REPO, a.preflight_dir, static.PREFLIGHT, "C270")
        self.mode = mode
        p = static.derive.load(a.closure_dir / "receipt.json", CLOSURE)
        need(
            mode in ("OFF", "ON")
            and p["status"] == "PASS_C292_CAPTURE_STATIC_CLOSURE"
            and p["derived_sha256"] == DERIVED
            and p["constructor_sha256"] == CONSTRUCTOR
            and p["original_provider_rejected"]
            and p["static_preflight_sha256"] == self.receipt_sha256
            and p["preflight_map_sha256"] == self.pre["static_map_sha256"]
            and p["kernel"] == self.pre["kernel"]
            and p["driver_deployment"] == self.pre["deployment_commit"]
            and sha(HERE.parent / "capture_profile/screen.py") == p["supervisor_sha256"]
            and sha(HERE.parent / "capture_profile/protocol.md") == p["protocol_sha256"]
            and sha(HERE.parent / "capture_profile/metadata-pairs.md")
            == p["metadata_addendum_sha256"],
            "historical static closure",
        )
        for label, q in p["queries"].items():
            for ext, key in [("out", "stdout_sha256"), ("err", "stderr_sha256")]:
                need(sha(a.closure_dir / (label + "." + ext)) == q[key], "closure evidence")
        source = SimpleNamespace(
            derived_dir=a.derived_dir,
            derived_sha256=DERIVED,
            constructor_sha256=CONSTRUCTOR,
            constructor_receipt=a.constructor_receipt,
        )
        manifest, row = static.metadata(source)
        need(
            str(manifest) == p["manifest"]
            and row["manifest_sha256"] == p["manifest_sha256"]
            and row["index_sha256"] == p["index_sha256"],
            "closure targets different metadata",
        )
        self.original_exe, self.original_search = self.exe, self.native_search
        exe, image, historical = static.historical(
            SimpleNamespace(bin_dir=Path(p["executable"]).parent)
        )
        self.backend = Path(historical["backend_root"]).resolve(strict=True)
        need(
            str(exe) == p["executable"]
            and p["binary_sha256"] == static.CAPTURE
            and p["library_sha256"] == static.C291,
            "historical binaries changed",
        )
        self.data_paths = {
            key: Path(path)
            for key, path in (
                ("model", row["model_path"]),
                ("pack", row["pack_path"]),
                ("manifest", manifest),
                ("index", manifest.with_name("integral-index.json")),
            )
        }
        self.data_stats = {key: row[key + "_stat"] for key in self.data_paths}
        search = p["explicit_search"]
        alias_dir = a.closure_dir / "libs"
        need(
            search == [str(alias_dir.resolve(strict=True)), *self.arm["native_search"]],
            "native closure search",
        )
        self.new_alias = alias_dir
        self.new_bindings = {static.SONAME: str(image)}
        aliases(alias_dir, self.new_bindings)
        listing = self.static.interpret(
            self.static.command(
                [self.static.LOADER, "--list", exe], self.static.environment(search)
            )
        )
        resolved = static.verify_listing(listing, self.links, alias_dir / static.SONAME, image)
        need(
            resolved == {k: v["file"] for k, v in p["startup"].items()},
            "startup resolution changed",
        )
        self.files = dict(self.files)
        self.files[str(exe)] = identity(exe) | {"sha256": static.CAPTURE}
        self.files[str(image)] = identity(image) | {"sha256": static.C291}
        need(
            all(
                self.files[path]["sha256"] == p["startup"][k]["sha256"]
                for k, path in resolved.items()
            ),
            "startup digest changed",
        )
        self.exe = exe
        self.arm = self.arm | dict(
            native_search=search, executable=str(exe), executable_sha256=static.CAPTURE
        )
        self.native_search = ":".join(search)
        self.links = {k: [str(path), resolved[k]] for k, path in listing.items()}
        self.initial = set(resolved.values())
        self.allowed = self.initial | set(map(str, self.drivers.values()))
        self.vma_keys = {path: reference_key(path, self.files[path]) for path in self.allowed}
        self.pack_observations = set()
        self.pack_seen = 0
        self.env_checked = False
        self.check_c55_before_first_live = None
        self.recheck()

    def recheck(self):
        super().recheck()
        if getattr(self, "check_c55_before_first_live", None) and not self.env_checked:
            self.check_c55_before_first_live()
        if hasattr(self, "new_alias"):
            aliases(self.new_alias, self.new_bindings)
            for key, path in self.data_paths.items():
                need(
                    static.derive.runtime_stat(path.stat()) == self.data_stats[key],
                    "changed data file: " + key,
                )

    def live(self, pid):
        seen = super().live(pid)
        proc = Path("/proc") / str(pid)
        if not self.env_checked:
            values = [
                e
                for e in (proc / "environ").read_bytes().split(b"\0")
                if e.startswith((STORE_ENV + "=").encode())
            ]
            expected = (
                [(STORE_ENV + "=" + str(self.data_paths["manifest"])).encode()]
                if self.mode == "ON"
                else []
            )
            need(values == expected, "live store environment")
            self.env_checked = True
        fds = proc_pack(proc, self.data_paths["pack"], self.data_stats["pack"])
        if fds:
            need(self.mode == "ON", "unexpected store descriptor in OFF")
            self.pack_seen += 1
            self.pack_observations.update(fds)
        return seen

    def fd_evidence(self):
        need(
            self.env_checked
            and bool(self.pack_seen) == (self.mode == "ON")
            and len(self.pack_observations) == int(self.mode == "ON"),
            "live pack FD/provenance missing",
        )
        return dict(
            fd_and_flags=sorted(self.pack_observations),
            positive_samples=self.pack_seen,
            model_and_pack_stat_verified=True,
            store_environment_verified=True,
        )
