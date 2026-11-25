"""One private C281 session. Capture first real post-text T1 call through T2 shutdown."""

import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
INT = HERE.parent


def imported(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = imported("t1_c281_base", INT / "conversation/profile.py")
pfj = imported("t1_trace_format", INT / "analyse.py")
need, sha, save = base.need, base.sha, base.save
PREVIOUS = "78c3a5bb34353d2b880b14bfa80634cd06dfe465beec529446206a8728af3f43"
ORACLE = "5eea9fd586bb4c56d63964ed75184f73d06b44d2d5ee9d6e428cbc014ff76ce2"
PREVIOUS_CODE = "303bb56bbdb2b680af878a90606af78b8bec0f1ed81d0fdd6c8285e73c8234b2"
METHOD = "da39ef172df1db0e700616ec8d6512d5a5f273a5fbc0a2e2e4581f6e674799f9"
MAX_SEALED = 24 * 2**20


def text_event(fragment):
    line = fragment.strip()
    if not line.startswith("data: ") or line[6:] == "[DONE]":
        return False
    obj = json.loads(line[6:])
    choices = obj["choices"]
    need(type(choices) is list and len(choices) <= 1, "single choice")
    if not choices:
        return False
    delta = choices[0]["delta"]
    values = [delta.get(key) for key in ("reasoning_content", "content")]
    need(isinstance(delta, dict) and all(x is None or type(x) is str for x in values), "SSE text")
    return any(x and x.strip() for x in values)


class FirstText:
    def __init__(self, path):
        self.path = path
        self.fragments = 0
        self.armed = None

    def saw(self, kind, fields):
        if kind != "SSE_FRAGMENT" or self.armed is not None:
            return
        self.fragments += 1
        if text_event(fields["fragment"]):
            before = time.monotonic_ns()
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            self.armed = dict(
                before_ns=before, after_ns=time.monotonic_ns(), fragment=self.fragments
            )

    @contextlib.contextmanager
    def observing(self, evidence):
        original = evidence.write
        need("write" not in vars(evidence), "already wrapped evidence")

        def write(kind, **fields):
            original(kind, **fields)
            self.saw(kind, fields)

        evidence.write = write
        try:
            yield
        finally:
            del evidence.write


def prefix_seal(journal):
    """Only complete records before the first all-zero slot, without reading T2."""
    h = hashlib.sha256()
    record = pfj.RECORD
    empty = bytes(record.size)
    count = 0
    active_call = None
    with journal.open("rb") as f:
        raw = f.read(pfj.HEADER.size)
        need(
            raw == pfj.HEADER.pack(b"TESYPF1\0", 1, record.size, 262144, 0, 0, 0, 0),
            "provisional PFJ1 header",
        )
        while block := f.read(1024 * record.size):
            need(len(block) % record.size == 0, "partial PFJ1 record")
            for i in range(0, len(block), record.size):
                entry = block[i : i + record.size]
                if entry == empty:
                    need(count and active_call is None, "incomplete last T1 call")
                    h.update(block[:i])
                    return dict(records=count, sha256=h.hexdigest(), bytes=count * record.size)
                row = pfj.Row(*record.unpack(entry))
                need(row.ns and 1 <= row.kind <= 28, "incomplete provisional record")
                if count == 0:
                    need(row.kind == 1 and row.a == 1, "first T1 call was not unitary")
                if row.kind == 1:
                    need(active_call is None and row.a == 1, "unexpected T1 call")
                    active_call = row.call
                elif row.kind == 2:
                    need(active_call == row.call, "mismatched T1 return")
                    active_call = None
                count += 1
            h.update(block)
    raise ValueError("PFJ1 exhausted before T2")


def sealed_prefix(journal, seal):
    n = seal["records"]
    need(0 < n < 262144 and seal["bytes"] == n * pfj.RECORD.size, "T1 seal size")
    with journal.open("rb") as f:
        f.seek(pfj.HEADER.size)
        data = f.read(seal["bytes"])
    need(
        len(data) == seal["bytes"] and hashlib.sha256(data).hexdigest() == seal["sha256"],
        "T1 prefix changed after T2",
    )
    return data


class Runtime(base.Runtime):
    def __init__(self, a, out, previous, numeric_dsos):
        super().__init__(a, out, previous, numeric_dsos)
        self.trigger = out / "raw/T1.trigger"
        self.native["TESY_PHASE_FD_TRIGGER"] = str(self.trigger)
        self.first_text = FirstText(self.trigger)
        self.t1_seal = None
        self.t1_seal_sha = None
        self.before_second_ns = None

    @contextlib.contextmanager
    def observe_posts(self):
        client = base.source.client
        names = ("stream_chat", "fetch", "launcher", "persistent_mappings")
        original = {name: getattr(client, name) for name in names}

        def stream(*args, **kwargs):
            self.turn += 1
            if self.turn == 1:
                need(not os.path.lexists(self.trigger), "trigger exists before T1")
                with self.first_text.observing(client._REQUEST_LOCAL.evidence):
                    result = original["stream_chat"](*args, **kwargs)
                need(self.first_text.armed is not None, "no nonblank T1 text")
                return result
            need(self.turn == 2 and self.first_text.armed, "unexpected POST")
            raw = self.out / "raw"
            t1 = base.read(raw / "T1-result.json")
            need(
                t1["accepted"] is True
                and t1["finish_reason"] == "stop"
                and t1["prefix_gate"] == t1["content_gate"] == "PASS"
                and sha(raw / "T2-input.json") == self.reference["historical_inputs"][1],
                "T1 completion or historical T2",
            )
            self.t1_seal = prefix_seal(self.journal)
            data = sealed_prefix(self.journal, self.t1_seal)
            records = [pfj.Row(*v) for v in pfj.RECORD.iter_unpack(data)]
            selection = self.select_t1(records)
            file = self.out / "before-t2-candidates.json"
            save(file, selection)
            self.t1_seal["candidate_file_sha256"] = sha(file)
            self.t1_seal["ordered_keys_sha256"] = {
                k: selection["capacities"][k]["ordered_keys_sha256"] for k in ("239", "353")
            }
            save(self.out / "before-t2.json", self.t1_seal | {"arm": self.first_text.armed})
            self.t1_seal_sha = sha(self.out / "before-t2.json")
            self.before_second_ns = time.monotonic_ns()
            return original["stream_chat"](*args, **kwargs)

        client.stream_chat = stream
        try:
            yield
        finally:
            for name, fn in original.items():
                setattr(client, name, fn)


def gate(a):
    need(
        sha(HERE / "capture.md") == METHOD
        and sha(INT / "conversation/profile.py") == PREVIOUS_CODE,
        "source protocol",
    )
    prior = base.pinned(a.prior_on_dir / "receipt.json", PREVIOUS)
    need(
        prior["status"] == "PASS_C281_PFJ_ON"
        and prior["model_launches"] == 1
        and sha(a.prior_on_dir / "raw/events.pfj") == prior["journal_sha256"]
        and prior["gates"]["bridge_sha256"] == a.bridge_sha256
        and prior["gates"]["fixture_sha256"] == a.fixture_sha256,
        "prior ON/C270",
    )
    oracle = base.pinned(INT / "warm_oracle/joint-r01.json", ORACLE)
    need(
        oracle["status"] == "PASS_SAME_INITIAL_SELECTION_FOR_TWO_FLOORS"
        and oracle["source"]["journal"] == prior["journal_sha256"],
        "joint warm oracle",
    )
    eligible = [
        row
        for group in oracle["joint"]["C281_M4_predicted_tokens"].values()
        for row in group["capacity"]
        if row["cap"] == 353 and row["volume_possible"] and row["first_floor_ns"] <= 10**10
    ]
    need(eligible, "even optimistic warm state fails")
    return prior


def after(a, out, rt, r, prior):
    need(
        rt.turn == 2 and rt.last_seen and rt.pid and rt.before_second_ns and rt.t1_seal,
        "incomplete two-post lifecycle",
    )
    r["native_ids"] = rt.observation
    r["trajectories"] = base.trajectories(out / "raw", r, a.historical)
    need(r["trajectories"] == prior["trajectories"], "C281 trajectory")
    need(
        rt.trigger.is_file()
        and not rt.trigger.is_symlink()
        and rt.trigger.stat().st_size == 0
        and rt.journal.is_file()
        and not rt.journal.is_symlink()
        and pfj.HEADER.size < rt.journal.stat().st_size <= MAX_SEALED,
        "PFJ size/trigger",
    )
    need(sha(out / "before-t2.json") == rt.t1_seal_sha, "T1 pre-POST sealed record")
    sealed_prefix(rt.journal, rt.t1_seal)
    selected = base.pinned(out / "before-t2-candidates.json", rt.t1_seal["candidate_file_sha256"])
    rows, h = pfj.read_journal(rt.journal)
    old, oldh = pfj.read_journal(a.prior_on_dir / "raw/events.pfj")
    need(oldh["journal_sha256"] == prior["journal_sha256"], "T2 reference")
    cut = rt.t1_seal["records"]
    need(
        rows[0].kind == 1
        and rows[0].a == 1
        and rows[0].begin >= rt.first_text.armed["before_ns"]
        and rows[0].ns <= rt.before_second_ns
        and cut < len(rows)
        and rows[cut].kind == 1
        and rows[cut].a == 5
        and rows[cut].begin >= rt.before_second_ns,
        "native T1/T2 boundaries",
    )
    cmd = rt.reference["server_command"]
    model = Path(cmd[cmd.index("-m") + 1])
    verifier = imported("t1_capture_review", HERE / "audit.py")
    need(
        json.loads(json.dumps(verifier.capture_prefix(rows[:cut]))) == selected,
        "pre-POST candidate changed",
    )
    result = verifier.audit(rows, h, old, model, rt.t1_seal)
    save(out / "boundary-audit.json", result)
    r.update(
        journal_sha256=h["journal_sha256"],
        journal_bytes=rt.journal.stat().st_size,
        boundary_audit_sha256=sha(out / "boundary-audit.json"),
        before_t2_sha256=sha(out / "before-t2.json"),
        captured_records=h["records"],
        prior_on_sha256=PREVIOUS,
        warm_oracle_sha256=ORACLE,
        time_comparability="NOT_QUALIFIED",
        arm_time=rt.first_text.armed,
    )
    need(result["status"] == "PASS", "boundary audit: " + result.get("gate", ""))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for opt in (
        "repo",
        "window",
        "placement",
        "c270",
        "historical",
        "preflight-dir",
        "build-dir",
        "fixture-dir",
        "startup-dir",
        "bridge-dir",
        "prior-on-dir",
        "new-output-dir",
    ):
        p.add_argument("--" + opt, required=True, type=Path)
    for opt in (
        "commit",
        "unit",
        "window-sha256",
        "preflight-sha256",
        "fixture-sha256",
        "bridge-sha256",
    ):
        p.add_argument("--" + opt, required=True)
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    a.mode, a.c270_sha256 = "ON", base.capture.C270
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    start = time.monotonic()
    r = {}
    try:
        need(
            a.repo.resolve(strict=True) == base.post.contract.REPO
            and base.source.git(a.repo, "rev-parse", "HEAD") == a.commit
            and not base.source.git(a.repo, "status", "--porcelain")
            and not base.source.relevant_environment(os.environ),
            "clean source and environment",
        )
        prior = gate(a)
        order = base.window_order(a.window, a.window_sha256, a.fixture_dir / "receipt.json")
        w = base.pinned(a.window / "receipt.json", a.window_sha256)
        policy = base.pinned(a.window / "resource-policy.json", w["canonical_policy_sha256"])
        stamp = datetime.fromisoformat(policy["snapshot"]["utc"])
        age = (datetime.now(UTC) - stamp).total_seconds()
        need(w["status"] == "PASS_RESOURCE_WINDOW_ONLY" and 0 <= age <= 3600, "C55 age/status")
        order["age_before_C118_s"] = age
        pins = base.prior(a)
        auditor = imported("t1_startup_preflight", HERE / "audit.py")
        need(
            callable(auditor.audit)
            and callable(auditor.capture_prefix)
            and time.get_clock_info("monotonic").implementation == "clock_gettime(CLOCK_MONOTONIC)",
            "audit/clock",
        )
        historical = base.capture.attest_history(a.historical)
        rt = Runtime(a, out, historical, pins)
        rt.select_t1 = auditor.capture_prefix
        if a.execute:
            r = rt.execute(a, out)
            need(r["status"] == "PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY", "client")
            after(a, out, rt, r, prior)
            r["status"] = "PASS_T1_VICTIM_WINDOW_AND_T2_REFERENCE"
        else:
            frozen = rt.actual_sources(rt.selection)
            need(
                base.post.contract.source_digest(rt.historical_projection(frozen))
                == base.read(base.post.SESSION / "inputs.json")["actual_inputs_sha256"],
                "origins",
            )
            original, digest = rt.numeric(a.c270)
            rt.bind_c270(a, original, digest)
            _, model = base.post.contract.placement(a.window, a.placement)
            need(model == original["model_stat"], "model placement")
            r.update(status="PREPARED_ONLY", model_launches=0)
        r.update(
            c55_order=order,
            c55_sha256=a.window_sha256,
            historical_manifest_sha256=base.samples.historic_manifest(a.historical),
            audit_program_sha256=sha(HERE / "audit.py"),
            fixture_sha256=a.fixture_sha256,
            numeric_bridge_sha256=a.bridge_sha256,
            loader_preflight_sha256=a.preflight_sha256,
            dso_build_sha256=base.BUILD,
        )
    except Exception as exc:
        r.update(
            status="FAIL_PRESERVED",
            failure=f"{type(exc).__name__}: {exc}",
            model_launches=len(list(out.glob("raw/*.launch.json"))),
        )
    r.update(
        mode="ON_T1_FIRST_TEXT",
        unit=a.unit,
        envelope_s=time.monotonic() - start,
        controller_sha256=sha(__file__),
        protocol_sha256=METHOD,
        commit=a.commit,
    )
    if r["envelope_s"] > 650:
        r.update(status="FAIL_PRESERVED", failure="650s envelope")
    save(out / "receipt.json", r)
    print(r["status"])
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
