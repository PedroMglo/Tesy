"""A one-SONAME refinement of the two previously admitted C269 process maps."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import FunctionType, SimpleNamespace

HERE = Path(__file__).resolve().parent
Q = HERE.parents[2]
REPO = Q.parents[1]
sys.path.insert(0, str(Q / "nvme_r0_gate/qualified_profile"))
from authority import Authority, identity, need, read, reference_key, sha  # noqa: E402

sys.path.insert(0, str(REPO / "tools"))
import run_bounded  # noqa: E402

SONAME = "libllama.so.0"
ORIGINAL = "347267b2e9cbf920dbf912d6aaf1884e5eff4cccc41c349e93c42bd6403a658f"
WORKER = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
RUNNER = "e6f404e06036ce9df9fcca048d193710e75b37729fc2df411bf417034a7d347b"
PROTOCOL = "488c94915394d88b0d5c83c61b2e98aef9fd85ce2abf938b9ca4b89452a910cd"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def child_ldd(search, program=None):
    """Run only the stock ldd query in the native selection, not the monitor or its telemetry."""
    need(sha(Path(run_bounded.__file__)) == RUNNER, "unrecognized monitor implementation")
    original = program or run_bounded.backend_library_hashes

    def ldd(args, *, text, timeout):
        need(
            len(args) == 2 and args[0] == "ldd" and text and timeout == 15,
            "unexpected helper invocation",
        )
        return subprocess.check_output(
            ["/usr/bin/ldd", args[1]],
            text=text,
            timeout=timeout,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LD_LIBRARY_PATH": search},
        )

    return FunctionType(
        original.__code__,
        original.__globals__ | {"subprocess": SimpleNamespace(check_output=ldd)},
        original.__name__,
        original.__defaults__,
        original.__closure__,
    )


def search_from_args(args):
    first = args.index("--")
    opts = args[:first]
    assignments = [opts[i + 1] for i, word in enumerate(opts) if word == "--env"]
    result = [
        e.removeprefix("LD_LIBRARY_PATH=") for e in assignments if e.startswith("LD_LIBRARY_PATH=")
    ]
    need(
        len(result) == 1 and result[0] and all(Path(z).is_absolute() for z in result[0].split(":")),
        "single explicit native library selection",
    )
    return result[0]


def numeric_census(expected, observed):
    need(expected and observed == expected, "live numerical DSOs differ from selected ldd")
    return {Path(k).name: v for k, v in expected.items()}


class LibraryAuthority(Authority):
    def __init__(self, preflight, pre_sha, build, build_sha, arm, mode):
        super().__init__(REPO, preflight, pre_sha, arm)
        need(
            mode in ("gold", "candidate") and sha(build / "receipt.json") == build_sha,
            "build identity",
        )
        b = read(build / "receipt.json")
        need(
            b["status"] == "PASS_C269_PHASE_FD_PRIVATE_BUILD"
            and b["worker_commit"] == WORKER
            and b["static_preflight_sha256"] == pre_sha
            and b["gold_sha256"] == b["original_sha256"] == ORIGINAL
            and b["candidate_sha256"] != ORIGINAL,
            "relinked/candidate authority",
        )
        image = (build / b[mode + "_file"]).resolve(strict=True)
        need(
            image.parent == (build / mode).resolve(strict=True)
            and image.name == Path(self.links[SONAME][1]).name
            and sha(image) == b[mode + "_sha256"],
            "selected image",
        )
        self.original_links = dict(self.links)
        self.original_search = self.native_search
        self.arm = dict(self.arm, native_search=[str(image.parent), *self.arm["native_search"]])
        self.native_search = ":".join(self.arm["native_search"])
        listed = self.static.interpret(
            self.static.command(
                [self.static.LOADER, "--list", self.exe],
                self.static.environment(self.arm["native_search"]),
            )
        )
        actual = {
            name: [str(path), str(path.resolve(strict=True))] for name, path in listed.items()
        }
        need(
            actual.keys() == self.links.keys()
            and all(value == self.links[name] for name, value in actual.items() if name != SONAME)
            and actual[SONAME] == [str(image.parent / SONAME), str(image)],
            "only libllama may change",
        )
        self.files = dict(self.files)
        self.files[str(image)] = identity(image) | {"sha256": b[mode + "_sha256"]}
        self.links = actual
        self.initial = {r[1] for r in actual.values()}
        self.allowed = self.initial | set(map(str, self.drivers.values()))
        self.vma_keys = {p: reference_key(p, self.files[p]) for p in self.allowed}
        by_name = {
            name: {"file": Path(row[1]).name, "sha256": self.files[row[1]]["sha256"]}
            for name, row in actual.items()
        }
        need(b["startup"][arm][mode] == by_name, "build/live startup witnesses")
        self.image = image
        self.image_sha = b[mode + "_sha256"]
        self.recheck()

    def recheck(self):
        super().recheck()
        if hasattr(self, "image"):
            permitted = {self.image.name, SONAME, "libllama.so"}
            need(
                all(
                    p.name in permitted and p.resolve(strict=True) == self.image
                    for p in self.image.parent.iterdir()
                    if ".so" in p.name
                ),
                "unexpected private ELF alias",
            )

    def smoke_log(self, prefix, pid):
        path = Path(str(prefix) + "." + str(pid))
        need(
            set(prefix.parent.glob(prefix.name + ".*")) == {path}
            and 0 < path.stat().st_size <= 8 << 20,
            "loader journal",
        )
        data = path.read_text()
        for line in data.splitlines():
            if line.strip():
                need(line.strip().split(":", 1)[0] == str(pid), "loader PID")
        loaded = self.loader.initialized(data, pid)
        self.loader.required_present(loaded, self.initial)
        names = self.origin.all_requests(data, pid)
        need(
            loaded <= self.allowed
            and names <= set(self.links) | set(self.drivers) | {self.origin.ABSENT},
            "unexpected initializer or request in no-model process",
        )
        return dict(
            sha256=sha(path),
            initialized={Path(f).name: self.files[f]["sha256"] for f in sorted(loaded)},
            requested=sorted(names),
        )
