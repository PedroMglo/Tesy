"""Bind one qualified natural P to BASE or the same private ELF with tracing OFF/ON."""

import contextlib
import os
import stat
import struct
import sys
import time
from pathlib import Path
from runpy import run_path
from types import FunctionType

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[4]
OLD = QUAL / "packed_nvme_manifest/server_profile/conversation"
sys.path.insert(0, str(OLD))
import transport_profile as p  # noqa: E402

need, sha, read, pinned = p.need, p.sha, p.conversation.read, p.pinned
MODES = ("BASE", "CONTROL", "OFF", "ON")
FIX = "TESY_PHASE_FD_FILE"
TRG = "TESY_PHASE_FD_TRIGGER"
PROTOCOL = "577fc2911826870beef46ded88c52c4c2dc03d66df32f98ce0bd531f3cefb0ef"
ADDENDUM = "b6fe810c89c413488388e47ae01f35609901ed21adadcacca41c3189fa5c9db3"
C292_TREE = "3b1c13734120f430d779960e3e8123eb58ffeee1947a1844636743b1e3aa1f03"


def with_globals(fn, **globals_):
    return FunctionType(
        fn.__code__, fn.__globals__ | globals_, fn.__name__, fn.__defaults__, fn.__closure__
    )


def selected(startup, candidate, sha256, previous):
    need(set(startup) == set(previous) and len(previous) == 24, "24 C281 objects")
    need(
        previous[p.SONAME]["sha256"] == p.live.static.C291 and sha256 != p.live.static.C291,
        "independent C291 control",
    )
    need(
        startup == previous | {p.SONAME: {"file": str(candidate), "sha256": sha256}},
        "foreign provider",
    )


def order_for(build, method):
    need(
        build["status"] == "PASS_C291_PACK_PFJ_DSO_STATIC_C281"
        and build["original_sha256"] == p.live.static.C291,
        "unfinished/original DSO",
    )
    if method == "exact":
        need(
            build.get("build_variant") != "current_compiler_control"
            and build["gold_sha256"] == p.live.static.C291,
            "exact gold changed",
        )
        return ("BASE", "OFF", "ON")
    need(
        method == "toolchain"
        and build.get("build_variant") == "current_compiler_control"
        and type(build["control_exec_same"]) is bool,
        "toolchain control criterion",
    )
    return ("BASE", "OFF", "ON") if build["control_exec_same"] else MODES


def bridge(a, build):
    need(a.bridge_dir is not None and a.bridge_sha256 is not None, "numeric bridge required")
    row = pinned(a.bridge_dir / "receipt.json", a.bridge_sha256)
    need(
        row["status"] == "PASS_C292_PACK_OBSERVER_NUMERIC"
        and row["build_receipt_sha256"] == a.build_sha256
        and row["libraries"]
        == {
            "original": p.live.static.C291,
            "control": build["control_sha256"],
            "overlay": build["candidate_sha256"],
        }
        and set(row["arms"]) == {"control_off", "overlay_off", "overlay_on"},
        "numeric bridge/ELF identity",
    )
    for name, key, enabled in (
        ("control_off", "control", False),
        ("overlay_off", "overlay", False),
        ("overlay_on", "overlay", True),
    ):
        arm = row["arms"][name]
        need(
            arm["status"] == "PASS_C292_ARM_NUMERICS"
            and arm["journal_enabled"] is enabled
            and arm["image_sha256"] == row["libraries"][key]
            and arm["capture_tree"]
            == {
                "files": 3266,
                "total_bytes": 88704231,
                "sha256_name_size_content_v1": C292_TREE,
            },
            "numeric arm identity",
        )
        pinned(a.bridge_dir / name / "receipt.json", arm["receipt_sha256"])
    return row


def admission(a):
    build = pinned(a.build_dir / "receipt.json", a.build_sha256)
    fixture = pinned(a.fixture_dir / "receipt.json", a.fixture_sha256)
    need(
        build["status"] == "PASS_C291_PACK_PFJ_DSO_STATIC_C281"
        and order_for(build, a.method)
        and build["static_preflight_sha256"] == a.preflight_sha256 == p.live.static.PREFLIGHT
        and build["c281_closure_sha256"] == p.CLOSURE,
        "production reference/control",
    )
    need(
        fixture["status"] == "PASS_PACK_NATIVE_FIXTURE_EXECUTIONS"
        and fixture["backend"] == "c89c88b342054223e3f27a17fbfd0954803147ac"
        and fixture["sources"]["observer.patch"]
        == build["patch_sha256"]
        == sha(HERE.parent / "observer.patch")
        and fixture["overlay"]["phase-fd-integrated.h"] == build["header_sha256"],
        "fixture/build mismatch",
    )
    actual = {"gguf-off", "gguf-on", "pack-off", "pack-on", "pack-short-on"}
    need(set(fixture["cases"]) == actual, "incomplete fixture")
    for label, files in fixture["cases"].items():
        need(
            "native.json" in files and ("journal.bin" in files) == label.endswith("-on"),
            "fixture artifacts",
        )
        for name, digest in files.items():
            need(
                Path(name).name == name and sha(a.fixture_dir / label / name) == digest,
                "fixture evidence",
            )
    run_path(HERE.parent / "audit.py")["inspect_family"](a.fixture_dir)
    original = pinned(a.closure_dir / "receipt.json", p.CLOSURE)
    image = a.build_dir.resolve(strict=True) / "candidate/libllama.so.0.0.9884"
    need(
        build["candidate_file"] == "candidate/libllama.so.0.0.9884"
        and image.resolve(strict=True) == image
        and sha(image) == build["candidate_sha256"],
        "candidate ELF",
    )
    selected(build["startup"], image, build["candidate_sha256"], original["startup"])
    if a.method == "toolchain":
        control = a.build_dir.resolve(strict=True) / "gold/libllama.so.0.0.9884"
        need(
            build["control_file"] == "gold/libllama.so.0.0.9884"
            and control.resolve(strict=True) == control
            and sha(control) == build["control_sha256"],
            "control ELF",
        )
        need(
            build["control_startup"]
            == original["startup"]
            | {p.SONAME: {"file": str(control), "sha256": build["control_sha256"]}},
            "foreign control dependency",
        )
    maps = build["per_mode"]
    need(
        maps["original"]["server"] == original["per_mode"]["on"]["server"]
        and maps["off"] == maps["on"]
        and maps["on"]["server"] == {k: v["file"] for k, v in build["startup"].items()},
        "old/new C281 closure",
    )
    need(
        len(build["queries"]) == 53 and set(build["consumers"]) == set(original["consumers"]),
        "relocations",
    )
    queries = dict(build["queries"])
    if a.method == "toolchain":
        need(
            len(build["control_queries"]) == 9
            and len(build["control_capture_queries"]) == 2
            and len(build["capture_queries"]) == 2,
            "recompiled control/C292 closures",
        )
        for key in ("control_queries", "capture_queries", "control_capture_queries"):
            need(not queries.keys() & build[key].keys(), "duplicate query label")
            queries.update(build[key])
    for label, query in queries.items():
        need(Path(label).name == label and query["returncode"] == 0, "failed query")
        for ext, key in (("out", "stdout_sha256"), ("err", "stderr_sha256")):
            need(sha(a.build_dir / "loader" / (label + "." + ext)) == query[key], "query outputs")
    return build


def overlay(authority, build, image, control):
    old = authority.links
    search = build["control_explicit_search" if control else "explicit_search"]
    need(
        Path(search[0]) == image.parents[1] / ("control-libs" if control else "libs")
        and search[1:] == authority.arm["native_search"][1:],
        "isolated overlay search",
    )
    alias = Path(search[0]) / p.SONAME
    p.live.aliases(alias.parent, {p.SONAME: str(image)})
    mapping = authority.static.interpret(
        authority.static.command(
            [authority.static.LOADER, "--list", authority.exe], authority.static.environment(search)
        )
    )
    resolved = p.screen.validate_map(mapping, old, alias, image, entire=True)
    expected = build["control_per_consumer"] if control else build["per_mode"]["on"]
    digest = build["control_sha256" if control else "candidate_sha256"]
    need(resolved == expected["server"], "selected overlay no longer present")
    authority.files = authority.files | {str(image): p.live.identity(image) | {"sha256": digest}}
    authority.links = {k: [str(path), resolved[k]] for k, path in mapping.items()}
    authority.arm = authority.arm | {"native_search": search}
    authority.native_search = ":".join(search)
    authority.initial = set(resolved.values())
    authority.allowed = authority.initial | set(map(str, authority.drivers.values()))
    authority.vma_keys = {k: p.live.reference_key(k, authority.files[k]) for k in authority.allowed}
    authority.recheck()


def observer_env(data, expected):
    rows = [
        b for b in data.split(b"\0") if any(b.startswith(k.encode() + b"=") for k in (FIX, TRG))
    ]
    need(
        sorted(rows) == sorted(os.fsencode(k + "=" + v) for k, v in expected.items()),
        "live journal environment",
    )


def journal_fd(proc, path, required):
    if not required:
        need(not os.path.lexists(path), "observer output in control")
        return None
    filestat = path.lstat()
    need(
        stat.S_ISREG(filestat.st_mode) and stat.S_IMODE(filestat.st_mode) == 0o600,
        "private journal",
    )
    found = []
    for fd in (proc / "fd").iterdir():
        try:
            if os.readlink(fd) == str(path):
                status = fd.stat()
                need(
                    (status.st_dev, status.st_ino) == (filestat.st_dev, filestat.st_ino),
                    "journal inode",
                )
                found.append({"fd": int(fd.name), "dev": status.st_dev, "ino": status.st_ino})
        except FileNotFoundError:
            continue
    need(len(found) == 1, "journal not owned by server")
    return found[0]


class Runtime(p.Runtime):
    def __init__(self, a, out, label):
        need(label in MODES, "observer mode")
        super().__init__(a, out, "P")
        self.build = admission(a)
        need(label in order_for(self.build, a.method), "unregistered arm")
        if a.method == "toolchain":
            bridge(a, self.build)
        self.label = label
        if label != "BASE":
            source = self.build["control_startup" if label == "CONTROL" else "startup"]
            self.image = Path(source[p.SONAME]["file"])
            overlay(self.authority, self.build, self.image, label == "CONTROL")
        self.journal = out / "raw/events.pfj"
        self.trigger = out / "raw/T2.trigger"
        self.extra = {FIX: str(self.journal), TRG: str(self.trigger)} if label == "ON" else {}
        self.native = (
            self.authority.child_env(self.prefix)
            | {p.live.STORE_ENV: str(self.paths["manifest"])}
            | self.extra
        )
        self.before_second_ns = None
        self.before_create_ns = None
        self.turn = 0
        self.jfds = []
        self.args = a

    def numeric(self, path):
        original, digest = super().numeric(path)
        # The original C292 bridge and the new static startup projection have separate authorities.
        if self.label == "BASE":
            return original, digest
        base = original["pinned"]
        name = self.image.name
        need(base["startup_dso_sha256"][name] == p.live.static.C291, "C292 original bridge")
        layout = base["startup_dso_sha256"] | {
            name: self.authority.files[str(self.image)]["sha256"]
        }
        return original | {"pinned": base | {"startup_dso_sha256": layout}}, digest

    def monitor_command(self, cmd, out):
        cmd = super().monitor_command(cmd, out)
        at = len(cmd) - len(self.command) - 1
        need(cmd[at] == "--" and cmd[at + 1 :] == self.command, "native argv")
        return (
            cmd[:at] + [v for k, s in self.extra.items() for v in ("--env", k + "=" + s)] + cmd[at:]
        )

    def witness(self, pid, point, name):
        super().witness(pid, point, name)
        proc = Path("/proc") / str(pid)
        observer_env((proc / "environ").read_bytes(), self.extra)
        self.jfds.append(journal_fd(proc, self.journal, self.label == "ON"))
        need(self.jfds[-1] == self.jfds[0], "journal FD changed")
        need(
            os.path.lexists(self.trigger) == (len(self.jfds) == 2 and self.label == "ON"),
            "trigger lifetime",
        )

    @contextlib.contextmanager
    def posts(self):
        client = p.session.client
        original = client.stream_chat

        def wrapped(*args, **kwargs):
            self.turn += 1
            if self.turn == 2:
                if self.label == "ON":
                    with self.journal.open("rb") as journal:
                        expected = struct.pack("<8s7Q", b"TESYPF1\0", 1, 96, 262144, 0, 0, 0, 0)
                        need(
                            journal.read(64) == expected and journal.read(96) == bytes(96),
                            "pretrigger journal already contains events",
                        )
                self.before_create_ns = time.monotonic_ns()
            p.conversation.trigger(
                self.trigger,
                "ON" if self.label == "ON" else "OFF",
                self.turn,
                self.out / "raw",
                self.reference["historical_inputs"],
            )
            if self.turn == 2:
                self.before_second_ns = time.monotonic_ns()
            return original(*args, **kwargs)

        client.stream_chat = wrapped
        try:
            yield
        finally:
            client.stream_chat = original

    def metadata(self):
        need(self.turn == 2 and self.before_second_ns and len(self.jfds) == 2, "cuts")
        if self.label == "ON":
            inode = self.journal.stat()
            need(
                self.jfds[0]["ino"] == inode.st_ino
                and self.jfds[0]["dev"] == inode.st_dev
                and self.trigger.is_file()
                and self.trigger.stat().st_size == 0
                and 64 < inode.st_size <= p.conversation.JOURNAL_MAX,
                "sealed journal identity",
            )
        else:
            need(
                not any(os.path.lexists(x) for x in (self.trigger, self.journal)),
                "inactive journal",
            )
        return dict(
            label=self.label,
            candidate_build_sha256=self.args.build_sha256,
            fixture_sha256=self.args.fixture_sha256,
            reference_numeric_sha256=p.screen.C292,
            numeric_scope="original_C291"
            if self.args.method == "exact"
            else "original_and_C292_pack_numeric_arms",
            new_numeric_bridge_sha256=self.args.bridge_sha256,
            index_path=str(self.paths["index"]),
            manifest_path=str(self.paths["manifest"]),
            trigger_check_begin_ns=self.before_create_ns,
            before_second_ns=self.before_second_ns,
            journal_sha256=sha(self.journal) if self.label == "ON" else None,
            journal_fd_cuts=self.jfds,
        )


def start(a, out, label):
    # Exercise the same clean checkout, historical startup and C55 guards used by P.
    return with_globals(
        p.starting, Runtime=lambda args, folder, _mode: Runtime(args, folder, label)
    )(a, out, "P")


def invoke(a, out, label, execute):
    rt = start(a, out, label)
    base = p.run_arm if execute else p.prepare_arm
    arm = with_globals(base, starting=lambda *_: rt)
    if not execute:
        return arm(a, out, "P") | {"label": label, "new_numeric_bridge_sha256": a.bridge_sha256}
    with rt.posts():
        result = arm(a, out, "P")
    try:
        result["pack_events"] = rt.metadata()
    except Exception:
        p.conversation.save(out / "closed-client-before-journal-check.json", result)
        raise
    return result
