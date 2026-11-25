"""Use the qualified natural P client with one earlier trigger and a T1-only seal."""

import contextlib
import os
import resource
import stat
import struct
import time
from functools import partial
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
FULL = HERE.parent
PACK = FULL.parent
prior = run_path(PACK / "conversation/family.py")
base = prior["acquisition"]
p, need, sha, pinned, save = base.p, base.need, base.sha, base.pinned, prior["save"]
POLICY = "e2ca80bf825b4d73b8f0ef85ef3a5fb3dd7393c5843089a57287f94f3322a785"
PROFILE = "c8039261d756635269eef9d5b1f37dac4dde1faeca5a53c126aa00c9a4963060"
OLD_FAMILY = "e5012e559a2403145abc6f5317bddc8b83f95f1e09b592eb83a6baa2c18980a9"
PROTOCOL = "dcd718cabf81ba90c757ac4cd627de6a230dc0a2daa67fe88d112807c61ad1db"
CAPACITY = 1398100
BYTES = 64 + CAPACITY * 96
LIMIT_NS = 15 * 10**9
POLICY_FILE = PACK / "natural_trace/prefill_retention/policy.py"


def require_private(path):
    s = path.lstat()
    need(
        stat.S_ISREG(s.st_mode) and stat.S_IMODE(s.st_mode) == 0o600 and s.st_uid == os.getuid(),
        "ordinary private file",
    )
    return s


def initial_journal(path):
    require_private(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        expected = struct.pack("<8s7Q", b"TESYFP1\0", 1, 96, CAPACITY, 0, 0, 0, 0)
        need(
            os.fstat(fd).st_size == BYTES and os.pread(fd, 160, 0) == expected + bytes(96),
            "pre-T1 journal already active or wrong layout",
        )
    finally:
        os.close(fd)


def record_seal(out, journal, audit_prefix, select, clock=time.monotonic_ns):
    began = clock()
    cpu_before = time.process_time_ns()
    hwm_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rows, proof = audit_prefix(journal)
    calls = sorted(proof["prefill_calls"])
    need(
        calls == list(range(1, 10)) and 0 < proof["records"] <= CAPACITY - 262144,
        "prefix cover/headroom",
    )
    need(isinstance(proof["sha256"], str) and len(proof["sha256"]) == 64, "prefix SHA")
    selection = select(rows, calls, capacity=353)
    del rows
    need(
        selection["policy_sha256"] == POLICY
        and selection["prefill_calls"] == calls
        and selection["capacity"] == 353
        and set(selection["banks"]) == {"lru", "prefill"}
        and all(len(v["ordered_keys"]) == v["held"] <= 353 for v in selection["banks"].values()),
        "private selected banks",
    )
    candidates = out / "before-t2-candidates.json"
    save(candidates, selection)
    digest = sha(candidates)
    need(pinned(candidates, digest) == selection, "candidate reread")
    seal = {
        **proof,
        "prefill_calls": calls,
        "candidate_file_sha256": digest,
        "policy_sha256": POLICY,
        "seal_start_ns": began,
        "selection_saved_ns": clock(),
        "seal_client_cpu_to_save_ns": time.process_time_ns() - cpu_before,
        "client_process_hwm_before_kib": hwm_before,
        "client_process_hwm_through_selection_kib": resource.getrusage(
            resource.RUSAGE_SELF
        ).ru_maxrss,
    }
    saved = out / "before-t2.json"
    save(saved, seal)
    sealed_sha = sha(saved)
    need(pinned(saved, sealed_sha) == seal, "seal reread")
    done = clock()
    need(
        began <= seal["selection_saved_ns"] <= done and done - began <= LIMIT_NS,
        "interturn seal deadline",
    )
    return seal, sealed_sha, done


def pre_second(raw, expected_hash):
    t1 = p.conversation.read(raw / "T1-result.json")
    need(
        t1["accepted"] is True
        and t1["finish_reason"] == "stop"
        and t1["content_gate"] == t1["prefix_gate"] == "PASS"
        and sha(raw / "T2-input.json") == expected_hash,
        "T1 terminal or T2 input changed",
    )


def admission(a):
    b = pinned(a.build_dir / "receipt.json", a.build_sha256)
    f = pinned(a.fixture_dir / "receipt.json", a.fixture_sha256)
    need(
        sha(PACK / "conversation/profile.py") == PROFILE
        and sha(POLICY_FILE) == POLICY
        and sha(HERE / "protocol.md") == PROTOCOL,
        "sources",
    )
    need(
        b["status"] == "PASS_C291_FULL_PREFIX_DSO_STATIC_C281"
        and b["original_sha256"] == p.live.static.C291
        and b["static_preflight_sha256"] == a.preflight_sha256 == p.live.static.PREFLIGHT
        and b["c281_closure_sha256"] == p.CLOSURE,
        "new static closure",
    )
    need(
        f["status"] == "PASS_FULL_PREFIX_NATIVE_CUT"
        and f["model_launches"] == 0
        and f["profile_patch_sha256"] == b["profile_patch_sha256"] == sha(FULL / "profile.patch")
        and f["header_sha256"] == b["profile_header_sha256"],
        "full-profile native gate",
    )
    image = a.build_dir.resolve(strict=True) / "candidate/libllama.so.0.0.9884"
    original = pinned(a.closure_dir / "receipt.json", p.CLOSURE)
    need(
        b["candidate_file"] == "candidate/libllama.so.0.0.9884"
        and image.resolve(strict=True) == image
        and sha(image) == b["candidate_sha256"],
        "new ELF",
    )
    base.selected(b["startup"], image, b["candidate_sha256"], original["startup"])
    need(
        b["per_mode"]["off"] == b["per_mode"]["on"]
        and b["per_mode"]["original"]["server"] == original["per_mode"]["on"]["server"]
        and len(b["queries"]) == 53
        and set(b["consumers"]) == set(original["consumers"]),
        "24-provider C281 closure",
    )
    for key in ("queries", "capture_queries", "control_queries", "control_capture_queries"):
        for label, q in b[key].items():
            need(label == Path(label).name and q["returncode"] == 0, "loader query")
            for ext, field in (("out", "stdout_sha256"), ("err", "stderr_sha256")):
                need(
                    sha(a.build_dir / "loader" / (label + "." + ext)) == q[field], "loader evidence"
                )
    run_path(FULL / "numeric/bridge.py")["verify_natural_gate"](
        a.bridge_dir, a.bridge_sha256, a.build_dir, a.build_sha256
    )
    return b


class Runtime(base.Runtime):
    def __init__(self, a, out, label):
        need(label in ("OFF", "ON"), "unknown arm")
        p.Runtime.__init__(self, a, out, "P")
        self.build = admission(a)
        self.label = label
        self.image = Path(self.build["startup"][p.SONAME]["file"])
        base.overlay(self.authority, self.build, self.image, False)
        self.obs = out / "observer"
        self.journal = self.obs / "events.pfj"
        self.trigger = self.obs / "T1.trigger"
        self.extra = (
            {base.FIX: str(self.journal), base.TRG: str(self.trigger)} if label == "ON" else {}
        )
        self.native = (
            self.authority.child_env(self.prefix)
            | {p.live.STORE_ENV: str(self.paths["manifest"])}
            | self.extra
        )
        self.args = a
        self.turn = 0
        self.jfds = []
        self.posts_ns = []
        self.trigger_ns = None
        self.seal_sha = None
        self.seal_end_ns = None

    def monitor_command(self, cmd, out):
        cmd = super().monitor_command(cmd, out)
        need(
            not any(x.startswith("LimitFSIZE=") for x in cmd) and cmd.count("-p") >= 3,
            "service limits",
        )
        i = cmd.index("--")
        need(cmd[0] == "systemd-run" and "MemorySwapMax=0" in cmd[:i], "original systemd envelope")
        return cmd[:i] + ["-p", "LimitFSIZE=134217728"] + cmd[i:]

    def witness(self, pid, point, name):
        p.Runtime.witness(self, pid, point, name)
        proc = Path("/proc") / str(pid)
        base.observer_env((proc / "environ").read_bytes(), self.extra)
        fd = base.journal_fd(proc, self.journal, self.label == "ON")
        self.jfds.append(fd)
        need(
            fd == self.jfds[0]
            and os.path.lexists(self.trigger) == (self.label == "ON" and len(self.jfds) == 2),
            "FD or trigger lifetime",
        )

    @contextlib.contextmanager
    def posts(self):
        self.obs.mkdir(mode=0o700)
        client = p.session.client
        original = client.stream_chat

        def stream(*args, **kwargs):
            self.turn += 1
            need(
                self.turn in (1, 2) and len(self.jfds) == 1, "POST before PID proof or outside pair"
            )
            raw = self.out / "raw"
            expected = self.reference["historical_inputs"]
            if self.turn == 1:
                need(
                    sha(raw / "T1-input.json") == expected[0] and not os.path.lexists(self.trigger),
                    "T1 input/cut",
                )
                if self.label == "ON":
                    initial_journal(self.journal)
                    self.trigger_ns = time.monotonic_ns()
                    fd = os.open(
                        self.trigger, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
                    )
                    os.close(fd)
            else:
                pre_second(raw, expected[1])
                if self.label == "ON":
                    need(self.trigger_ns and self.trigger.stat().st_size == 0, "trigger missing")
                    seal, self.seal_sha, self.seal_end_ns = record_seal(
                        self.out,
                        self.journal,
                        partial(
                            self.audit["seal_before_post"],
                            pack_identity=self.stats["pack"],
                            model_identity=self.stats["model"],
                        ),
                        self.selector,
                    )
            entered = time.monotonic_ns()
            if self.turn == 2 and self.label == "ON":
                need(entered - seal["seal_start_ns"] <= LIMIT_NS, "selection expired before POST")
            self.posts_ns.append(entered)
            return original(*args, **kwargs)

        client.stream_chat = stream
        try:
            yield
        finally:
            client.stream_chat = original

    def metadata(self):
        need(
            self.turn == len(self.posts_ns) == len(self.jfds) == 2
            and self.posts_ns[0] < self.posts_ns[1],
            "two witnessed POSTs",
        )
        result = {
            "label": self.label,
            "post_entry_ns": self.posts_ns,
            "trigger_before_open_ns": self.trigger_ns,
            "journal_fd_cuts": self.jfds,
            "candidate_build_sha256": self.args.build_sha256,
            "new_numeric_bridge_sha256": self.args.bridge_sha256,
            "fixture_sha256": self.args.fixture_sha256,
        }
        if self.label == "OFF":
            need(
                not any(self.jfds) and not any(self.obs.iterdir()) and self.seal_sha is None,
                "OFF artifacts",
            )
            return result
        s = require_private(self.journal)
        need(
            s.st_ino == self.jfds[0]["ino"]
            and s.st_dev == self.jfds[0]["dev"]
            and 64 < s.st_size <= BYTES,
            "closed journal identity",
        )
        need(require_private(self.trigger).st_size == 0, "trigger")
        sealed = pinned(self.out / "before-t2.json", self.seal_sha)
        candidates = pinned(self.out / "before-t2-candidates.json", sealed["candidate_file_sha256"])
        need(
            self.trigger_ns
            <= self.posts_ns[0]
            < sealed["seal_start_ns"]
            <= self.seal_end_ns
            <= self.posts_ns[1]
            and self.posts_ns[1] - sealed["seal_start_ns"] <= LIMIT_NS,
            "POST order and seal deadline",
        )
        projection = self.audit["audit_closed"](
            self.journal, sealed, self.stats["pack"], self.stats["model"]
        )
        need(
            projection["status"] == "PASS_FULL_PREFIX_NATURAL_JOURNAL"
            and projection["t2_enter_ns"] >= self.posts_ns[1],
            "T2 native clock before POST",
        )
        first = next(self.audit["iter_rows"](self.journal, 0, 1))
        last = next(self.audit["iter_rows"](self.journal, sealed["records"] - 1, 1))
        need(
            first.kind == 1
            and first.call == 1
            and last.kind == 2
            and last.call == 86
            and self.posts_ns[0] <= first.ns <= last.ns <= sealed["seal_start_ns"],
            "native T1 boundaries/POST",
        )
        replay = self.selector(
            self.audit["iter_rows"](self.journal, 0, sealed["records"]),
            sealed["prefill_calls"],
            capacity=353,
        )
        need(replay == candidates, "selection changed after native cleanup")
        save(self.out / "journal-audit.json", projection)
        return result | {
            "seal_end_ns": self.seal_end_ns,
            "before_t2_sha256": self.seal_sha,
            "t1_candidates_sha256": sealed["candidate_file_sha256"],
            "prefix_records": sealed["records"],
            "candidate_counts": {k: v["held"] for k, v in candidates["banks"].items()},
            "journal_sha256": sha(self.journal),
            "journal_bytes": s.st_size,
            "journal_audit_sha256": sha(self.out / "journal-audit.json"),
        }


def invoke(a, out, label, execute):
    ctor = base.with_globals(
        p.starting, Runtime=lambda args, folder, _: Runtime(args, folder, label)
    )
    rt = ctor(a, out, "P")
    rt.audit = run_path(FULL / "audit.py")
    rt.selector = run_path(POLICY_FILE)["seal"]
    if not execute:
        return base.with_globals(p.prepare_arm, starting=lambda *_: rt)(a, out, "P")
    fn = base.with_globals(p.run_arm, starting=lambda *_: rt)
    with rt.posts():
        result = fn(a, out, "P")
    try:
        result["full_prefix"] = rt.metadata()
    except Exception:
        save(out / "closed-client-before-journal-check.json", result)
        raise
    return result
