"""Bind the unchanged C281 two-turn client to R (C269), O (C291) or P (C291 + store)."""

import importlib.util
import os
import select
import signal
import threading
import time
from pathlib import Path
from types import FunctionType, SimpleNamespace

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[2]
INTEGRATED = QUAL / "phase_fd/integrated"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


conversation = module("store_c281_trajectories", INTEGRATED / "conversation/profile.py")
live = module("store_c292_live", HERE.parents[1] / "capture_numeric/live.py")
screen = module("store_c281_closure", HERE.parent / "screen.py")
capture, post, session = conversation.capture, conversation.post, conversation.source
need, sha, pinned = conversation.need, conversation.sha, conversation.pinned
SONAME = screen.SONAME
CLOSURE = "9e553bcfa3dd8889100c8836bc3b873491248567672f93e7859e7f8b76e35116"
MODES = {"R": "original", "O": "off", "P": "on"}


def numerical_pair(path):
    pair = pinned(path, screen.C292)
    need(
        pair["status"] == "PASS_SELECTED_C292_NVME_PAIR"
        and pair["closure_sha256"] == live.CLOSURE
        and pair["model_launch_receipts"] == 2
        and pair["unexecuted_arms"] == [],
        "C292 numeric family",
    )
    selections = []
    for mode, arm in zip(("OFF", "ON"), pair["arms"], strict=True):
        folder = path.parent / mode
        row = pinned(folder / "receipt.json", arm["receipt_sha256"])
        need(
            arm["mode"] == mode
            and row["status"] == arm["status"] == "PASS_C292_" + mode
            and row["child_exit"] == 0
            and row["scope_cleanup"]
            and row["monitor_stop"] is None
            and row["model_launch_receipts"] == 1,
            "C292 numeric child",
        )
        resource = pinned(folder / "resource-store.json", row["resource_sha256"])
        gold = pinned(folder / "numerical.json", row["numerical_sha256"])
        selected = pinned(folder / "selected.json", row["c127_sha256"])
        session.check_gate(selected)
        need(
            resource["metadata_sha256"] == live.DERIVED
            and resource["static_receipt_sha256"] == live.CLOSURE
            and gold == row["numerical"]
            and gold["status"] == "PASS_C292_ARM_NUMERICS"
            and gold["reference_receipt_sha256"] == capture.C270,
            "C292 pinned C270 reference",
        )
        startup = resource["pinned"]["startup_dso_sha256"]
        need(
            all(row["loader"]["initialized_sha256"].get(k) == v for k, v in startup.items()),
            "C292 live startup evidence",
        )
        selections.append(startup)
    need(selections[0] == selections[1], "C292 numerical runtime mismatch")
    return selections[0]


def bound_startup(old, observed, image_name, mode):
    """Require exactly the one ELF substitution separately witnessed by the C292 pair."""
    need(
        mode in MODES
        and old[image_name] == live.static.C269
        and observed == (old | {image_name: live.static.C291}),
        "C270/C292 provider delta",
    )
    return old if mode == "R" else observed


def input_files(a, authority, mode):
    closure = pinned(a.closure_dir / "receipt.json", CLOSURE)
    need(
        mode in MODES
        and a.preflight_sha256 == live.static.PREFLIGHT
        and closure["status"] == "PASS_C281_C291_STATIC_CLOSURE"
        and closure["preflight_sha256"] == a.preflight_sha256
        and closure["derived_sha256"] == live.DERIVED
        and closure["constructor_sha256"] == live.CONSTRUCTOR
        and closure["static_map_sha256"] == authority.pre["static_map_sha256"]
        and closure["kernel"] == authority.pre["kernel"]
        and closure["driver_deployment"] == authority.pre["deployment_commit"]
        and closure["source_sha256"] == sha(HERE.parent / "screen.py")
        and closure["protocol_sha256"] == sha(HERE.parent / "protocol.md")
        and closure["original_receipt_sha256"] == capture.HISTORY
        and closure["numerical_pair_sha256"] == screen.C292
        and closure["original_and_candidate_rejected_as_each_other"]
        and len(closure["queries"]) == 53
        and closure["binary_sha256"] == capture.SERVER
        and closure["server"] == str(authority.exe),
        "C281 static closure chain",
    )
    for label, row in closure["queries"].items():
        for ext, field in (("out", "stdout_sha256"), ("err", "stderr_sha256")):
            need(sha(a.closure_dir / (label + "." + ext)) == row[field], "C281 query " + label)
    manifest, metadata = live.static.metadata(
        SimpleNamespace(
            derived_dir=a.derived_dir,
            derived_sha256=live.DERIVED,
            constructor_receipt=a.constructor_receipt,
            constructor_sha256=live.CONSTRUCTOR,
        )
    )
    need(
        str(manifest) == closure["manifest"]
        and all(metadata[k] == closure[k] for k in ("manifest_sha256", "index_sha256"))
        and metadata["model_stat"]["dev"] == metadata["pack_stat"]["dev"],
        "pack placement",
    )
    paths = {
        "model": Path(metadata["model_path"]),
        "pack": Path(metadata["pack_path"]),
        "manifest": manifest,
        "index": manifest.with_name("integral-index.json"),
    }
    return closure, paths, {k: metadata[k + "_stat"] for k in paths}


def install_selection(authority, closure, mode):
    """Check the live ld.so listing against the full 24-object closure and retain its VMA keys."""
    search = authority.arm["native_search"]
    alias, image = map(Path, authority.links[SONAME])
    originals = {k: v[1] for k, v in authority.links.items()}
    candidate = Path(closure["startup"][SONAME]["file"])
    need(
        sha(image) == live.static.C269
        and sha(candidate) == live.static.C291
        and originals == closure["per_mode"]["original"]["server"]
        and closure["explicit_search"][1:] == search,
        "provider images",
    )
    if mode != "R":
        search = closure["explicit_search"]
        alias, image = Path(search[0]) / SONAME, candidate
        live.aliases(alias.parent, {SONAME: str(candidate)})
    listed = authority.static.interpret(
        authority.static.command(
            [authority.static.LOADER, "--list", authority.exe], authority.static.environment(search)
        )
    )
    resolved = screen.validate_map(listed, authority.links, alias, image, entire=True)
    need(resolved == closure["per_mode"][MODES[mode]]["server"], "C281 selected listing")
    if mode != "R":
        authority.files = authority.files | {
            str(candidate): live.identity(candidate) | {"sha256": live.static.C291}
        }
        need(
            {k: {"file": v, "sha256": authority.files[v]["sha256"]} for k, v in resolved.items()}
            == closure["startup"],
            "C281 startup digests",
        )
        authority.links = {k: [str(p), resolved[k]] for k, p in listed.items()}
        authority.arm = authority.arm | {"native_search": search}
        authority.native_search = ":".join(search)
        authority.initial = set(resolved.values())
        authority.allowed = authority.initial | set(map(str, authority.drivers.values()))
        authority.vma_keys = {
            p: live.reference_key(p, authority.files[p]) for p in authority.allowed
        }
    authority.recheck()
    return image


def cut(proc, paths, stats, mode):
    """Inspect both payload identities and flags at the same already-owned client cut."""
    values = [
        v
        for v in (proc / "environ").read_bytes().split(b"\0")
        if v.startswith((live.STORE_ENV + "=").encode())
    ]
    expected = [(live.STORE_ENV + "=" + str(paths["manifest"])).encode()] if mode == "P" else []
    need(values == expected, "live store environment")
    descriptors = {"pack": [], "model": []}
    for fd in (proc / "fd").iterdir():
        try:
            target = os.readlink(fd)
            if not target.startswith("/"):
                continue
            stat = live.static.derive.runtime_stat(fd.stat())
            keys = [
                k
                for k in descriptors
                if target.removesuffix(" (deleted)") == str(paths[k])
                or (stat["dev"], stat["inode"]) == (stats[k]["dev"], stats[k]["inode"])
            ]
            if not keys:
                continue
            flags = [
                int(line.split()[1], 8)
                for line in (proc / "fdinfo" / fd.name).read_text().splitlines()
                if line.startswith("flags:")
            ]
            need(len(keys) == 1 and target == os.readlink(fd), "unstable store descriptor")
        except FileNotFoundError:
            continue
        k = keys[0]
        need(
            target == str(paths[k])
            and stat == stats[k]
            and paths[k].is_file()
            and len(flags) == 1
            and not flags[0] & os.O_PATH
            and flags[0] & os.O_DIRECT
            and flags[0] & os.O_ACCMODE == os.O_RDONLY,
            "foreign, buffered or writable " + k,
        )
        descriptors[k].append({"fd": int(fd.name), "flags": flags[0]})
    for rows in descriptors.values():
        rows.sort(key=lambda r: r["fd"])
    need(
        len(descriptors["pack"]) == int(mode == "P") and descriptors["model"],
        "payload descriptor cardinality",
    )
    return descriptors


class Runtime(capture.Runtime):
    def __init__(self, a, out, mode):
        need(mode in MODES, "transport arm")
        super().__init__(a, out, capture.attest_history(a.history_dir))
        closure, self.paths, self.stats = input_files(a, self.authority, mode)
        self.mode = mode
        self.numeric_dsos = numerical_pair(a.c292_receipt)
        self.image = install_selection(self.authority, closure, mode)
        self.native = self.authority.child_env(self.prefix)
        if mode == "P":
            self.native[live.STORE_ENV] = str(self.paths["manifest"])
        configured = self.command[self.command.index("-m") + 1]
        need(Path(configured).samefile(self.paths["model"]), "server model/pack source")
        self.cuts = []
        self.exit_thread = None
        self.exit_observed_ns = None
        self.owner_signal = None

    def recheck_data(self):
        for k, p in self.paths.items():
            need(
                not p.is_symlink() and live.static.derive.runtime_stat(p.stat()) == self.stats[k],
                "changed backing file: " + k,
            )
        if self.mode != "R":
            live.aliases(Path(self.authority.arm["native_search"][0]), {SONAME: str(self.image)})
        self.authority.recheck()

    def actual_sources(self, selector):
        base = post.contract.sources(selector)
        self.original = base["dso"][SONAME]
        need(self.original["sha256"] == live.static.C269, "historical C269 provider")
        self.selected = {
            "path": str(self.image),
            "sha256": self.authority.files[str(self.image)]["sha256"],
        }
        return base | {"dso": base["dso"] | {SONAME: self.selected}}

    def historical_projection(self, frozen):
        need(frozen["dso"][SONAME] == self.selected, "actual provider projection")
        return post.projection(frozen | {"dso": frozen["dso"] | {SONAME: self.original}})

    def numeric(self, path):
        self.original_numeric, digest = session.validate_c270(path)
        need(digest == capture.C270, "C270 receipt changed")
        pinned = self.original_numeric["pinned"]
        startup = bound_startup(
            pinned["startup_dso_sha256"], self.numeric_dsos, self.image.name, self.mode
        )
        return self.original_numeric | {"pinned": pinned | {"startup_dso_sha256": startup}}, digest

    def bind_c270(self, a, g, digest):
        need(
            g["pinned"]["startup_dso_sha256"][self.image.name] == self.selected["sha256"],
            "numeric provider selection",
        )
        self.recheck_data()
        super().bind_c270(a, self.original_numeric, digest)

    def monitor_command(self, cmd, out):
        need(out == self.out, "monitor destination")
        base = {k: self.native[k] for k in post.NATIVE_KEYS}
        cmd = post.monitor_argv(cmd, self.authority.monitor_dir, base)
        original = str(post.contract.REPO / "tools/run_bounded.py")
        need(cmd.count(original) == 1, "original process monitor")
        cmd[cmd.index(original)] = str(INTEGRATED / "profile/monitor.py")
        sep = len(cmd) - len(self.reference["server_command"]) - 1
        need(
            cmd[sep] == "--" and cmd[sep + 1 :] == self.reference["server_command"],
            "original C281 argv",
        )
        opts = (
            ["--env", live.STORE_ENV + "=" + self.native[live.STORE_ENV]]
            if self.mode == "P"
            else []
        )
        return cmd[:sep] + opts + ["--"] + self.command

    def watch_exit(self, pid):
        fd = os.pidfd_open(pid)

        def observe():
            try:
                p = select.poll()
                p.register(fd, select.POLLIN)
                if any(events & select.POLLIN for _, events in p.poll(650_000)):
                    self.exit_observed_ns = time.monotonic_ns()
            finally:
                os.close(fd)

        self.exit_thread = threading.Thread(target=observe, daemon=True)
        try:
            self.exit_thread.start()
        except Exception:
            os.close(fd)
            raise

    def owner_stop(self, pid, sig):
        before = time.monotonic_ns()
        os.killpg(pid, sig)
        self.owner_signal = (pid, sig, before, time.monotonic_ns())

    def witness(self, pid, point, name):
        super().witness(pid, point, name)
        self.recheck_data()
        identity = session.process_identity(pid)
        if not self.cuts:
            self.watch_exit(pid)
        row = cut(Path("/proc") / str(pid), self.paths, self.stats, self.mode)
        need(session.process_identity(pid) == identity, "recycled identity during FD census")
        if self.cuts:
            need(
                identity == self.cuts[0]["identity"] and row == self.cuts[0]["fds"],
                "payload descriptors or server changed",
            )
        self.cuts.append(
            dict(point=point, identity=identity, fds=row, monotonic_ns=time.monotonic_ns())
        )

    def finish(self, identity, manifest, out, rid):
        self.exit_thread.join(timeout=2)
        self.cleanup_observed_ns = time.monotonic_ns()
        need(
            self.owner_signal
            and self.owner_signal[:2] == (identity["pid"], signal.SIGINT)
            and self.exit_observed_ns is not None,
            "owner signal and process exit witness",
        )
        begin, end = self.owner_signal[2:]
        need(
            self.cuts[-1]["monotonic_ns"] <= begin <= end <= self.cleanup_observed_ns
            and begin <= self.exit_observed_ns <= self.cleanup_observed_ns,
            "shutdown ordering",
        )
        need(
            len(self.cuts) == 2 and self.cuts[-1]["identity"] == identity,
            "missing end-to-end FD proof",
        )
        self.recheck_data()
        return super().finish(identity, manifest, out, rid)


def starting(a, out, mode):
    need(out.is_dir() and not out.is_symlink() and not any(out.iterdir()), "new arm directory")
    need(
        a.repo.resolve(strict=True) == post.contract.REPO
        and session.git(a.repo, "rev-parse", "HEAD") == a.commit
        and not session.git(a.repo, "status", "--porcelain"),
        "measurement checkout",
    )
    need(
        a.c270_sha256 == capture.C270
        and sha(a.window / "receipt.json") == a.window_sha256
        and sha(Path(session.__file__)) == conversation.ORIGINAL_SESSION
        and not session.relevant_environment(os.environ),
        "profile inputs/overrides",
    )
    return Runtime(a, out, mode)


def prepare_arm(a, out, mode):
    rt = starting(a, out, mode)
    frozen = rt.actual_sources(rt.selection)
    need(
        post.contract.source_digest(rt.historical_projection(frozen))
        == post.load(post.SESSION / "inputs.json")["actual_inputs_sha256"]
        and frozen["server_command"] == rt.reference["server_command"],
        "historical C281 sources",
    )
    gate, digest = rt.numeric(a.c270)
    prior = post.c270_evidence(a, rt.original_numeric, digest, rt.pre, rt.smap)
    _, model = post.contract.placement(a.window, a.placement)
    need(
        gate["model_stat"] == model
        and all(
            any(Path(v["path"]).name == k and v["sha256"] == h for v in frozen["dso"].values())
            for k, h in gate["pinned"]["startup_dso_sha256"].items()
        ),
        "numeric certificate / ELF / placement",
    )
    rt.recheck_data()
    return dict(
        status="PREPARED_ONLY",
        mode=mode,
        model_launches=0,
        closure_sha256=CLOSURE,
        c292_sha256=screen.C292,
        libllama_sha256=rt.selected["sha256"],
        **prior,
    )


def run_arm(a, out, mode):
    started = time.monotonic()
    rt = starting(a, out, mode)
    base = session.campaign
    scoped = FunctionType(
        base.__code__,
        base.__globals__
        | {
            "sources": rt.actual_sources,
            "validate_c270": rt.numeric,
            "os": SimpleNamespace(environ=os.environ, fstat=os.fstat, killpg=rt.owner_stop),
        },
        base.__name__,
        base.__defaults__,
        base.__closure__,
    )
    result = scoped(a, out, rt)
    result["native_ids"] = rt.observation
    result["trajectories"] = conversation.trajectories(out / "raw", result, a.history_dir)
    result["transport"] = dict(
        mode=mode,
        closure_sha256=CLOSURE,
        c292_sha256=screen.C292,
        derived_sha256=live.DERIVED,
        constructor_sha256=live.CONSTRUCTOR,
        libllama=rt.selected,
        data_stat=rt.stats,
        cuts=rt.cuts,
        shutdown=dict(
            sigint_before_ns=rt.owner_signal[2],
            sigint_after_ns=rt.owner_signal[3],
            pidfd_exit_observed_ns=rt.exit_observed_ns,
            server_port_scope_verified_ns=rt.cleanup_observed_ns,
        ),
        post_client_to_verified_cleanup_ns=rt.cleanup_observed_ns - rt.cuts[-1]["monotonic_ns"],
    )
    result["envelope_s"] = time.monotonic() - started
    need(result["envelope_s"] <= 650, "650 s arm envelope")
    return result
