"""Track the integrated main executable and a single private libllama through load and exit."""

from pathlib import Path

import evaluate

OLD = evaluate.load(evaluate.FB.parent / "profile.py", "original_b3_supervisor")
library = evaluate.load(evaluate.Q / "phase_fd/integrated/profile/linkage.py", "library_checks")
need, sha = evaluate.need, evaluate.sha
FLAG = "TESY_B3_ROUTER_ROW"


class Authority(library.LibraryAuthority):
    def __init__(self, args, build):
        library.Authority.__init__(
            self, args.checkout, args.preflight_dir, args.preflight_sha256, "C270"
        )
        self.template_exe = self.exe
        self.original_search = self.native_search
        self.exe = (args.build_dir / "client/b3-numeric").resolve(strict=True)
        image = (args.build_dir / build["candidate_file"]).resolve(strict=True)
        name = library.SONAME
        need(
            image.name == Path(self.links[name][1]).name
            and image.parent == (args.build_dir / "candidate").resolve(strict=True)
            and sha(image) == build["candidate_sha256"]
            and sha(self.exe) == build["client_sha256"],
            "private executable or library",
        )
        self.arm = dict(
            self.arm,
            executable=str(self.exe),
            executable_sha256=build["client_sha256"],
            native_search=[str(image.parent), *self.arm["native_search"]],
        )
        self.native_search = ":".join(self.arm["native_search"])
        probs = self.static.interpret(
            self.static.command(
                [self.static.LOADER, "--list", self.exe],
                self.static.environment(self.arm["native_search"]),
            )
        )
        actual = {n: [str(p), str(p.resolve(strict=True))] for n, p in probs.items()}
        need(
            actual.keys() == self.links.keys()
            and all(actual[n] == self.links[n] for n in actual if n != name)
            and actual[name] == [str(image.parent / name), str(image)],
            "unexpected numerical provider",
        )
        self.links = actual
        self.files = dict(self.files)
        for f, h in ((image, build["candidate_sha256"]), (self.exe, build["client_sha256"])):
            self.files[str(f)] = library.identity(f) | {"sha256": h}
        self.initial = {v[1] for v in self.links.values()}
        self.allowed = self.initial | set(map(str, self.drivers.values()))
        self.vma_keys = {p: library.reference_key(p, self.files[p]) for p in self.allowed}
        self.image, self.image_sha = image, build["candidate_sha256"]
        need(
            {
                k: {"file": Path(v[1]).name, "sha256": self.files[v[1]]["sha256"]}
                for k, v in self.links.items()
            }
            == build["startup"]["candidate"],
            "stale build closure",
        )
        self.recheck()


def adjust(command, repo, previous, selected, mode):
    need(mode in ("OFF", "ON", "AR"), "experimental mode")
    cmd = list(command)
    for a, b in [
        (str(repo / "tools/run_bounded.py"), str(library.HERE / "monitor.py")),
        ("LD_LIBRARY_PATH=" + previous, "LD_LIBRARY_PATH=" + selected),
    ]:
        need(cmd.count(a) == 1, "original monitor/child search")
        cmd[cmd.index(a)] = b
    end = cmd.index("--", cmd.index("--env"))
    need(not any(x.startswith(FLAG + "=") for x in cmd), "prior switch")
    if mode == "ON":
        cmd[end:end] = ["--env", FLAG + "=1"]
    return cmd


def monitor_check(m, protocol, env, mode, measure):
    actual = m["relevant_environment"]
    need(
        m["explicit_env"] == env
        and (FLAG in actual) == (mode == "ON")
        and all(
            actual.get(k) == v for k, v in env.items() if k not in ("LD_DEBUG", "LD_DEBUG_OUTPUT")
        )
        and "LD_PRELOAD" not in actual,
        "effective router and loader selection",
    )
    standard = {k: v for k, v in env.items() if k != FLAG}
    OLD.base.check_native_manifest(
        dict(m, explicit_env=standard), protocol, protocol["pinned"], standard, measure
    )
