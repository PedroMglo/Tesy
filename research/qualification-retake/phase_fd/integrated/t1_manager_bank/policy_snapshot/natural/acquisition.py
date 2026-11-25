"""Collect the qualified C281 responses with PFJ1 armed at T1's first text in both sessions."""

import os
import stat
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
INT = HERE.parents[2]
controller = run_path(INT / "t1_capture/controller.py")
conv = controller["base"]
aud = conv.imported("policy_natural_audit", INT / "t1_capture/audit.py")
snapshot = conv.imported("natural_snapshot_format", HERE.parent / "review.py")
pfj = controller["pfj"]
need, sha, read, save = conv.need, conv.sha, conv.read, conv.save
ENV = "TESY_PFJ_POLICY_SNAPSHOT"
PFJ_CONTROL = "911b3be5b529d8e07409c12cf600ca9f7f6182f7a397fc6de265e5ea4be254eb"
FIXTURE = "e689fd19a7d78b5fb8833e63f761ebb2d46895953d970f534f1d4ea8dcb04264"


def owned_file(path, pid, accmode, expected_size):
    disk = path.lstat()
    need(
        stat.S_ISREG(disk.st_mode)
        and stat.S_IMODE(disk.st_mode) == 0o600
        and disk.st_size == expected_size
        and disk.st_nlink == 1,
        "private output identity",
    )
    fds = []
    for fd in Path(f"/proc/{pid}/fd").iterdir():
        try:
            access = fd.stat()
        except FileNotFoundError:
            continue
        if (access.st_dev, access.st_ino) == (disk.st_dev, disk.st_ino):
            info = Path(f"/proc/{pid}/fdinfo/{fd.name}").read_text().splitlines()
            (flags,) = (int(line.split()[1], 8) for line in info if line.startswith("flags:"))
            need(flags & os.O_ACCMODE == accmode and flags & os.O_CLOEXEC, "file descriptor mode")
            fds.append(int(fd.name))
    need(len(fds) == 1, "observer file not owned uniquely by server PID")
    return dict(pid=pid, fd=fds[0], dev=disk.st_dev, ino=disk.st_ino)


class Runtime(controller["Runtime"]):
    def __init__(self, a, out, ref, parent_pins):
        conv.capture.Runtime.__init__(self, a, out, ref)
        self.authority = conv.link.LibraryAuthority(
            a.preflight_dir, a.preflight_sha256, a.build_dir, a.build_sha256, "C281", "candidate"
        )
        self.native = self.authority.child_env(self.prefix)
        self.snapshot_mode = a.mode
        self.parent_pins = parent_pins
        self.mode, self.turn = "ON", 0  # PFJ1 itself is enabled in both sessions.
        self.journal, self.trigger = out / "raw/events.pfj", out / "raw/T1.trigger"
        self.policy = out / "raw/policy.bin"
        self.native.update(
            TESY_PHASE_FD_FILE=str(self.journal), TESY_PHASE_FD_TRIGGER=str(self.trigger)
        )
        if a.mode == "ON":
            self.native[ENV] = str(self.policy)
        self.first_text = controller["FirstText"](self.trigger)
        self.t1_seal = self.t1_seal_sha = self.before_second_ns = None
        self.select_t1 = aud.capture_prefix
        self.fd_proofs = {}

    def numeric(self, path):
        original, digest = conv.source.validate_c270(path)
        parent = original["pinned"]["startup_dso_sha256"]
        name = self.authority.image.name
        need(
            digest == conv.capture.C270
            and parent[name] == conv.link.ORIGINAL
            and self.parent_pins == parent | {name: PFJ_CONTROL},
            "independent C270 parent",
        )
        self.base_numeric = original
        # session.campaign separately verifies every digest against the selected C281 ELF.
        self.numeric_dsos = parent | {name: self.authority.image_sha}
        return original | {
            "pinned": original["pinned"] | {"startup_dso_sha256": self.numeric_dsos}
        }, digest

    def live_files(self, pid, point):
        row = {"journal": owned_file(self.journal, pid, os.O_RDWR, conv.JOURNAL_MAX)}
        if self.snapshot_mode == "ON":
            row["policy"] = owned_file(self.policy, pid, os.O_WRONLY, 0)
        else:
            need(
                not os.path.lexists(self.policy) and ENV not in self.native,
                "unexpected OFF policy file",
            )
        if self.fd_proofs:
            need(row == self.fd_proofs["first"], "native observer file identity changed")
        self.fd_proofs[point] = row

    def first(self, pid):
        super().first(pid)
        if "first" not in self.fd_proofs:
            self.live_files(pid, "first")

    def last(self, pid):
        super().last(pid)
        self.live_files(pid, "last")


def structural(rows, start):
    """Hash callback shapes and ordered logical rank rows."""
    roles = {1: [], 3: [], 9: [], 27: []}
    for r in rows:
        if r.call >= start and r.kind in roles:
            row = [r.call - start + 1, r.tile, r.layer, r.wave, r.a, r.b]
            if r.kind in (1, 3):
                row.append(r.c)
            roles[r.kind].append(row)
    need(all(roles.values()), "missing geometry or logical ranks")
    return dict(
        t2_geometry_sha256=aud.digest([roles[k] for k in (1, 3, 9)]),
        t2_route_sha256=aud.digest(roles[27]),
        t2_rank_rows=len(roles[27]),
        t2_remaps=len(roles[9]),
    )


def verify_sidecar(path, enter):
    values, table = snapshot.parse_policy(path.read_bytes())
    status, matches, call, n, first, last, calls, interval, *others = values
    need(
        (status, matches, call, n, first, last) == (1, 1, enter.call, 5, 2044, 2048)
        and (enter.kind, enter.a, enter.b, enter.c) == (1, 5, 2044, 2048)
        and calls >= 0
        and interval >= 0
        and others == [4, 36, 40, 128, 0, 0, 0],
        "TPOLICY1 target entry or queue/claim/loading",
    )
    need(
        len(table) == 36
        and all(0 <= v <= layer[0] for layer in table for v in layer[1:41])
        and all(0 <= v <= 2**32 - 1 for layer in table for v in layer[41:]),
        "policy values",
    )
    return {
        "status": status,
        "matches": matches,
        "call": call,
        "manager_calls": calls,
        "decay_interval": interval,
        "layers": 36,
        "slots_per_layer": 40,
    }


def after(a, out, rt, rec, prior):
    need(
        rt.pid and rt.last_seen and rt.turn == 2 and rt.before_second_ns and rt.t1_seal,
        "incomplete native/client lifecycle",
    )
    rec["native_ids"] = rt.observation
    rec["trajectories"] = conv.trajectories(out / "raw", rec, a.historical)
    need(rec["trajectories"] == prior["trajectories"], "independent trajectories")
    need(
        rt.trigger.is_file()
        and not rt.trigger.is_symlink()
        and rt.trigger.stat().st_size == 0
        and 64 < rt.journal.stat().st_size <= conv.JOURNAL_MAX
        and sha(out / "before-t2.json") == rt.t1_seal_sha,
        "trigger, journal or T1 seal",
    )
    controller["sealed_prefix"](rt.journal, rt.t1_seal)
    rows, h = pfj.read_journal(rt.journal)
    cut = rt.t1_seal["records"]
    chosen = conv.pinned(out / "before-t2-candidates.json", rt.t1_seal["candidate_file_sha256"])
    need(
        chosen == aud.capture_prefix(rows[:cut])
        and chosen["capacities"]["353"]["identified"]
        and rows[0].begin >= rt.first_text.armed["before_ns"]
        and rows[0].ns <= rt.before_second_ns
        and rows[cut].kind == 1
        and rows[cut].a == 5
        and rows[cut].begin >= rt.before_second_ns
        and rows[cut].call == chosen["t1_calls"] + 1,
        "before/after POST or T1 selection",
    )
    model = rt.reference["server_command"]
    current = aud.conservation(rows, h, Path(model[model.index("-m") + 1]), rows[cut].call)
    geom = [(c["tokens"], c["positions"], c["tiles"]) for c in current["calls"]]
    expected = [(5, [2044, 2048], [5]), (148, [2049, 2196], [32, 32, 32, 32, 20])]
    expected += [(1, [p, p], [1]) for p in range(2197, 2243)]
    need(geom[chosen["t1_calls"] :] == expected and current["fd_identity_checked"], "T2 graph/GGUF")
    old, oh = pfj.read_journal(a.prior_on_dir / "raw/events.pfj")
    signature = structural(rows[cut:], rows[cut].call)
    need(
        oh["journal_sha256"] == aud.PRIOR == prior["journal_sha256"]
        and signature == structural(old, 1),
        "historical ranks/callback geometry",
    )
    need(set(rt.fd_proofs) == {"first", "last"}, "missing live FD")
    for label, f in rt.fd_proofs["last"].items():
        final = (rt.policy if label == "policy" else rt.journal).lstat()
        need(
            (final.st_dev, final.st_ino) == (f["dev"], f["ino"]) and stat.S_ISREG(final.st_mode),
            "post-join output differs from live descriptor",
        )
    policy = None
    if a.mode == "ON":
        policy = verify_sidecar(rt.policy, rows[cut])
        slots, fifo, _ = aud.state_before(rows[:cut])
        need(
            not fifo and all(state != 1 and claim == 0 for _, _, state, claim in slots),
            "own PFJ1 differs from sidecar occupancy",
        )
    else:
        need(not os.path.lexists(rt.policy), "OFF produced a policy")
    save(out / "journal-audit.json", current)
    rec.update(
        signature,
        journal_audit_sha256=sha(out / "journal-audit.json"),
        journal_sha256=h["journal_sha256"],
        journal_bytes=rt.journal.stat().st_size,
        policy_sha256=sha(rt.policy) if policy else None,
        policy=policy,
        policy_bytes=rt.policy.stat().st_size if policy else 0,
        observer_fds=rt.fd_proofs,
        prefix_records=cut,
        before_t2_sha256=rt.t1_seal_sha,
        arm_time=rt.first_text.armed,
        before_second_ns=rt.before_second_ns,
        t1_candidates_sha256=rt.t1_seal["candidate_file_sha256"],
        t1_result_sha256=sha(out / "raw/T1-result.json"),
        t2_result_sha256=sha(out / "raw/T2-result.json"),
    )
