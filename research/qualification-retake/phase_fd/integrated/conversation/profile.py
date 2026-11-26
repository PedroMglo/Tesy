"""Observe the second C281 request. Each invocation owns exactly one fresh server."""

import argparse
import contextlib
import hashlib
import importlib.util
import json
import math
import os
import sys
import time
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path
from types import FunctionType

HERE = Path(__file__).resolve().parent
INT = HERE.parent
QUAL = INT.parents[1]
IDS = QUAL / "history_lookup/native_ids"
sys.path.insert(0, str(INT / "profile"))


def imported(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


link = imported("pfj_conversation_link", INT / "profile/linkage.py")
capture = imported("pfj_conversation_debug", IDS / "profile.py")
samples = imported("pfj_conversation_samples", IDS / "verify.py")
post = capture.post
source = post.session
need, sha, read, save = link.need, link.sha, link.read, post.save
SONAME = link.SONAME
BUILD = "e5042bfb23527a1763b28ca2098c0a00700383d07ff403a97d52da4bcdf422a6"
SMOKE = "0d7d2dbd7993c1e16e1bbd7d77a4d1955754658e0b4fabe10819ad5fc026cb6a"
VERIFIED = "494101d84e2696670bf59589768c3a7208db1c6b0b5ac1f6f914d3d9f264f08d"
PROTOCOL = "72269b49e2b17a63a0b17650a7cddcfc532f590f180d988948d7e547753e5988"
ORIGINAL_SESSION = "435c1381939a6ade6eda67c460695ea1e99cfb428ad8b8831a6c9b551fc27f4e"
DENOMINATORS = "29425b51a1037e8099d7b56a4f69ae0ccbf30df88633007a3db4a79fd97d2b6c"
METRICS = ("prefill_s", "decode_s", "first_final_s", "valid_wall_s")
JOURNAL_MAX = 64 + 262144 * 96


def pinned(path, digest):
    need(sha(path) == digest, "changed " + path.name)
    return read(path)


def projected_digest(row):
    return hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def paired_cost(off, on):
    def ratios(a, b):
        result = {}
        for key in METRICS:
            x, y = a[key], b[key]
            need(all(math.isfinite(v) and v > 0 for v in (x, y)), "invalid clock: " + key)
            result[key] = y / x
        return result

    need(len(off) == len(on) == 2, "two turns per arm")
    values = [ratios(a, b) for a, b in zip(off, on, strict=True)]
    return {
        "ON_over_OFF": values,
        "T2_within_band": all(0.85 <= v <= 1.15 for v in values[1].values()),
    }


def trigger(path, mode, turn, raw, history):
    need(mode in ("OFF", "ON") and turn in (1, 2), "POST order")
    need(not os.path.lexists(path), "pre-existing trigger")
    if turn == 1:
        return
    completed = read(raw / "T1-result.json")
    inp = raw / "T2-input.json"
    need(
        completed["accepted"] is True
        and completed["finish_reason"] == "stop"
        and completed["content_gate"] == completed["prefix_gate"] == "PASS"
        and sha(inp) == history[1],
        "T1 terminal or T2 workload",
    )
    if mode == "ON":
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(fd)


def window_order(window, receipt_sha, fixture):
    r = pinned(window / "receipt.json", receipt_sha)
    samples_file = window / "samples.jsonl"
    need(sha(samples_file) == r["window_sha256"], "C55 sample identity")
    with samples_file.open() as stream:
        first = json.loads(stream.readline())
    start = datetime.fromisoformat(first["utc"]).timestamp() - first["elapsed_s"]
    need(start >= fixture.stat().st_mtime, "C55 began before local publication of fixture")
    return {
        "samples_sha256": r["window_sha256"],
        "start_unix_s": start,
        "fixture_local_mtime_ns": fixture.stat().st_mtime_ns,
    }


def prompt_budget(row, phase):
    # Outward rounding of durations already published in seconds by the reference client.
    n = Decimal(10**9)

    def ns(key, rounding):
        return int((Decimal(str(row[key])) * n).to_integral_value(rounding=rounding))

    need(row["predicted_n"] == 47, "nominal denominator")
    base = 10**10 + ns("prefill_s", ROUND_CEILING) + ns("decode_s", ROUND_CEILING)
    base -= ns("first_final_s", ROUND_FLOOR)

    def price(count):
        budget = base - count * 10**9 // 6
        return {
            "denominator": count,
            "conditional_prompt_budget_ns_upper": budget,
            "scenario_bytes_at_4_5GBps": max(0, (budget * 4_500_000_000 + 10**9 - 1) // 10**9),
        }

    return {
        "C281_M4_predicted_tokens": price(47),
        "optimistic_AR_post_first_evaluations": price(46),
        "compulsory_payload_floor_bytes": phase["compulsory_payload_floor"],
        "relaxed_40slot_payload_floor_bytes": phase["relaxed_40slot_payload_floor"],
        "completed_in_calls_returned_bytes": phase["completed_in_calls_returned_bytes"],
        "origin_returned_bytes": phase["origin_returned_bytes"],
        "returned_after_prefill_for_origin_bytes": phase["returned_after_prefill_for_origin_bytes"],
    }


def prior(a):
    pair = pinned(a.bridge_dir / "receipt.json", a.bridge_sha256)
    need(
        pair["status"] == "PASS_C270_PAIRED_NUMERIC_AND_JOURNAL"
        and pair["model_launch_receipts"] == 2
        and pair["smoke_sha256"] == SMOKE
        and pair["build_sha256"] == BUILD
        and pair["reference_r0_sha256"] == capture.C270
        and pair["fixture_sha256"] == a.fixture_sha256
        and len(pair["arms"]) == 2,
        "numeric family",
    )
    build = pinned(a.build_dir / "receipt.json", BUILD)
    need(
        build["status"] == "PASS_C269_PHASE_FD_PRIVATE_BUILD"
        and build["static_preflight_sha256"] == a.preflight_sha256,
        "build/preflight",
    )
    fixture = pinned(a.fixture_dir / "receipt.json", a.fixture_sha256)
    need(
        fixture["status"] == "PASS_C269_PHASE_FD_MANAGER_AND_BOUNDARIES"
        and fixture["candidate_sha256"] == build["candidate_sha256"]
        and fixture["build_sha256"] == BUILD
        and set(fixture["arms"]) == {"off-ok", "on-ok", "off-short", "on-short", "on-inherited"},
        "real manager fixture",
    )
    smoke = pinned(a.startup_dir / "receipt.json", SMOKE)
    need(
        smoke["status"] == "PASS_C270_C281_ONE_PROVIDER_STARTUP"
        and smoke["build_sha256"] == BUILD
        and smoke["preflight_sha256"] == a.preflight_sha256
        and smoke["finished_processes"] == 6
        and smoke["model_launches"] == 0,
        "VMA gate",
    )
    pins = []
    for label, arm in zip(("OFF", "ON"), pair["arms"], strict=True):
        d = a.bridge_dir / label
        need(arm["mode"] == label and arm["model_launch_receipts"] == 1, "C270 arm order")
        r = pinned(d / "receipt.json", arm["receipt_sha256"])
        need(
            r["status"] == arm["status"] == "PASS_C270_" + label
            and r["model_launch_receipts"] == 1
            and r["monitor_stop"] is None,
            "C270 terminal",
        )
        grade = pinned(d / "selected.json", r["selected_sha256"])
        need(grade == r["numerical_gate"], "C270 grade")
        source.check_gate(grade)
        schema = read(d / "resource-phase.json")
        ctrl = pinned(d / "phase-control.json", r["phase_control_sha256"])
        need(
            sha(d / "resource-phase.json") == ctrl["resource_sha256"]
            and ctrl["image_sha256"] == build["candidate_sha256"]
            and ctrl["build_sha256"] == BUILD
            and r["authority"]["initialized_sha256"][Path(build["candidate_file"]).name]
            == build["candidate_sha256"],
            "numeric library identity",
        )
        raw = d / "raw"
        unit = schema["execution_scope_unit"]
        need(Path(unit).name == unit, "C270 unit")
        mon = pinned(raw / (unit + ".json"), r["monitor_sha256"])
        launch = pinned(raw / (unit + ".launch.json"), r["launch_sha256"])
        need(
            mon["process_identity"] == launch["process_identity"]
            and mon["returncode"] == 0
            and mon["stop_reason"] is None,
            "numeric launch/monitor",
        )
        if label == "ON":
            j = raw / "phase.pfj1"
            report = pinned(d / "journal-audit.json", r["journal_audit_sha256"])
            need(
                sha(j) == r["journal_sha256"]
                and j.stat().st_size == r["journal_bytes"] > 64
                and report["status"] == "PASS"
                and report["journal_sha256"] == r["journal_sha256"]
                and [c["tokens"] for c in report["calls"]] == [189] + [1] * 32,
                "numeric PFJ1",
            )
        pins.append(schema["pinned"]["startup_dso_sha256"])
    need(pins[0] == pins[1], "C270 runtime mismatch")
    return pins[0]


class Runtime(capture.Runtime):
    def __init__(self, a, out, reference, numeric_dsos):
        super().__init__(a, out, reference)
        self.authority = link.LibraryAuthority(
            a.preflight_dir, a.preflight_sha256, a.build_dir, BUILD, "C281", "candidate"
        )
        self.native = self.authority.child_env(self.prefix)
        self.mode = a.mode
        self.journal = out / "raw/events.pfj"
        self.trigger = out / "raw/T2.trigger"
        self.turn = 0
        self.numeric_dsos = numeric_dsos
        if self.mode == "ON":
            self.native.update(
                TESY_PHASE_FD_FILE=str(self.journal), TESY_PHASE_FD_TRIGGER=str(self.trigger)
            )

    def actual_sources(self, selector):
        base = post.contract.sources(selector)
        need(base["dso"][SONAME]["sha256"] == link.ORIGINAL, "original R0 selection")
        self.r0_dso = base["dso"][SONAME]
        return base | {
            "dso": base["dso"]
            | {SONAME: {"path": str(self.authority.image), "sha256": self.authority.image_sha}}
        }

    def historical_projection(self, actual):
        need(
            actual["dso"][SONAME]
            == {"path": str(self.authority.image), "sha256": self.authority.image_sha},
            "unexpected experimental selection",
        )
        return post.projection(actual | {"dso": actual["dso"] | {SONAME: self.r0_dso}})

    def numeric(self, path):
        baseline, digest = source.validate_c270(path)
        old = baseline["pinned"]["startup_dso_sha256"]
        image = self.authority.image.name
        need(
            digest == capture.C270
            and old[image] == link.ORIGINAL
            and self.numeric_dsos == (old | {image: self.authority.image_sha}),
            "one authorized C270 delta",
        )
        # The historical checks retain their independent input; only the subsequent ELF comparison
        # in session.campaign consumes the authenticated integrated C270 startup witness.
        self.base_numeric = baseline
        return baseline | {
            "pinned": baseline["pinned"] | {"startup_dso_sha256": self.numeric_dsos}
        }, digest

    def bind_c270(self, a, g, digest):
        need(g["pinned"]["startup_dso_sha256"] == self.numeric_dsos, "integrated C270 witness")
        super().bind_c270(a, self.base_numeric, digest)

    def monitor_command(self, cmd, out):
        # Inject the three established native loader variables via the historical supervisor.
        base = {k: self.native[k] for k in post.NATIVE_KEYS}
        cmd = post.monitor_argv(cmd, self.authority.monitor_dir, base)
        original = str(post.contract.REPO / "tools/run_bounded.py")
        need(
            out == self.out
            and cmd.count(original) == 1
            and self.reference["server_command"] == cmd[-len(self.reference["server_command"]) :],
            "original monitor/server",
        )
        cmd[cmd.index(original)] = str(INT / "profile/monitor.py")
        at = cmd.index("--")
        cmd[at:at] = ["-p", "LimitFSIZE=33554432"]
        last = len(cmd) - len(self.reference["server_command"]) - 1
        need(cmd[last] == "--", "server command separator")
        options = [
            item
            for k in self.native
            if k not in base
            for item in ("--env", k + "=" + self.native[k])
        ]
        return cmd[:last] + options + ["--"] + self.command

    @contextlib.contextmanager
    def observe_posts(self):
        client = source.client
        names = ("stream_chat", "fetch", "launcher", "persistent_mappings")
        before = {n: getattr(client, n) for n in names}

        def stream(*args, **kwargs):
            self.turn += 1
            trigger(
                self.trigger,
                self.mode,
                self.turn,
                self.out / "raw",
                self.reference["historical_inputs"],
            )
            if self.turn == 2:
                self.before_second_ns = time.monotonic_ns()
            return before["stream_chat"](*args, **kwargs)

        client.stream_chat = stream
        try:
            yield
        finally:
            for name, fn in before.items():
                setattr(client, name, fn)

    def execute(self, a, out):
        need(sha(Path(source.__file__)) == ORIGINAL_SESSION, "C281 session source")
        code = source.campaign
        scoped = FunctionType(
            code.__code__,
            code.__globals__ | {"sources": self.actual_sources, "validate_c270": self.numeric},
            code.__name__,
        )
        with self.observe_posts():
            return scoped(a, out, self)


def trajectories(raw, rec, historical):
    verified = pinned(IDS / "evidence/verified.json", VERIFIED)
    log = raw / rec["native_ids"]["raw_stderr_file"]
    need(sha(log) == rec["native_ids"]["stderr_sha256"], "sampling trace")
    steps = samples.trajectories(log.read_bytes())
    rows = []
    for i, (g, turn, ref) in enumerate(
        zip(samples.GEOMETRY, steps, verified["turns"], strict=True), 1
    ):
        actual = samples.projection(raw, i, g)
        need(
            actual == samples.projection(historical / "raw", i, g),
            "official history/choices/settings",
        )
        token_hash = samples.digest(samples.ids_bytes([token for token, _ in turn]))
        need(
            token_hash == ref["sampled_ids_sha256"]
            and samples.digest(samples.ids_bytes(actual[0]["official_ids"]))
            == ref["official_ids_sha256"]
            == rec["rows"][i - 1]["official_ids_sha256"],
            "native trajectory differs",
        )
        rows.append(
            dict(
                sampled_ids_sha256=token_hash,
                projected_sha256=projected_digest(actual),
                completion_n=len(turn),
                frames=len(actual[2]),
                feed_echoes=len(turn) - 1,
            )
        )
    return rows


def after(a, out, runtime, r):
    need(
        runtime.turn == 2 and runtime.last_seen and runtime.pid and runtime.before_second_ns,
        "two posts and closed listener",
    )
    r["native_ids"] = runtime.observation
    r["trajectories"] = trajectories(out / "raw", r, a.historical)
    if a.mode == "OFF":
        need(
            not any(os.path.lexists(p) for p in (runtime.journal, runtime.trigger)),
            "observer output in OFF",
        )
        return
    need(
        runtime.trigger.is_file()
        and not runtime.trigger.is_symlink()
        and runtime.trigger.stat().st_size == 0
        and runtime.journal.is_file()
        and not runtime.journal.is_symlink()
        and 64 < runtime.journal.stat().st_size <= JOURNAL_MAX,
        "trigger or journal missing",
    )
    analyzer = imported("pfj_conversation_analyse", INT / "analyse.py")
    rows, h = analyzer.read_journal(runtime.journal)
    argv = runtime.reference["server_command"]
    result = analyzer.audit(rows, h, Path(argv[argv.index("-m") + 1]))
    save(out / "journal-audit.json", result)
    r.update(
        journal_sha256=sha(runtime.journal),
        journal_bytes=runtime.journal.stat().st_size,
        journal_audit_sha256=sha(out / "journal-audit.json"),
        trigger_before_post_ns=runtime.before_second_ns,
    )
    need(
        result["status"] == "PASS"
        and [i["tokens"] for i in result["calls"]] == [5, 148] + [1] * 46
        and [i["tiles"] for i in result["calls"]] == [[5], [32, 32, 32, 32, 20]] + [[1]] * 46,
        "journal/phase geometry",
    )
    need(
        time.get_clock_info("monotonic").implementation == "clock_gettime(CLOCK_MONOTONIC)"
        and result["calls"][0]["start_ns"] >= runtime.before_second_ns,
        "T2 clock/trigger ordering",
    )
    r["own_ON_price"] = prompt_budget(r["rows"][1], result["nominal_prefill"])


def admit_off(a, gates):
    if a.mode == "OFF":
        need(a.off_dir is None and a.off_sha256 is None, "unexpected OFF dependency")
        return None
    need(a.off_dir is not None and a.off_sha256 is not None, "first complete OFF required")
    off = pinned(a.off_dir / "receipt.json", a.off_sha256)
    need(
        off["status"] == "PASS_C281_PFJ_OFF"
        and off["gates"] == gates
        and off["mode"] == "OFF"
        and off["model_launches"] == 1
        and off["cleanup"] == "SERVER_EXIT_0_OWNER_STOP_UNIT_CLOSED_PORT_AVAILABLE",
        "wrong OFF family",
    )
    return off


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for k in (
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
        "new-output-dir",
    ):
        parser.add_argument("--" + k, type=Path, required=True)
    for k in (
        "commit",
        "unit",
        "window-sha256",
        "preflight-sha256",
        "fixture-sha256",
        "bridge-sha256",
    ):
        parser.add_argument("--" + k, required=True)
    parser.add_argument("--off-dir", type=Path)
    parser.add_argument("--off-sha256")
    parser.add_argument("--mode", choices=("OFF", "ON"), required=True)
    parser.add_argument("--execute", action="store_true")
    a = parser.parse_args()
    a.c270_sha256 = capture.C270
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    before = time.monotonic()
    r = {}
    try:
        need(
            a.repo.resolve(strict=True) == post.contract.REPO
            and source.git(a.repo, "rev-parse", "HEAD") == a.commit
            and not source.git(a.repo, "status", "--porcelain")
            and sha(HERE / "protocol.md") == PROTOCOL
            and sha(HERE / "denominadores.md") == DENOMINATORS
            and not source.relevant_environment(os.environ),
            "research freeze",
        )
        order = window_order(a.window, a.window_sha256, a.fixture_dir / "receipt.json")
        pins = prior(a)
        gates = dict(
            bridge_sha256=a.bridge_sha256,
            fixture_sha256=a.fixture_sha256,
            smoke_sha256=SMOKE,
            original_c270_sha256=capture.C270,
            build_sha256=BUILD,
            c55_sha256=a.window_sha256,
            c55_order=order,
            preflight_sha256=a.preflight_sha256,
            measurement_commit=a.commit,
            historical_manifest_sha256=samples.historic_manifest(a.historical),
        )
        off = admit_off(a, gates)
        rt = Runtime(a, out, capture.attest_history(a.historical), pins)
        if a.execute:
            r = rt.execute(a, out)
            need(r["status"] == "PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY", "C281 client")
            after(a, out, rt, r)
            if off:
                need(r["trajectories"] == off["trajectories"], "OFF/ON work differs")
                r["paired_cost"] = paired_cost(off["rows"], r["rows"])
                r["clock_transfer"] = (
                    "WITHIN_PREREGISTERED_PAIRED_BAND"
                    if r["paired_cost"]["T2_within_band"]
                    else "INCONCLUSIVE_OUTSIDE_PAIRED_BAND"
                )
            r["status"] = "PASS_C281_PFJ_" + a.mode
        else:
            frozen = rt.actual_sources(rt.selection)
            need(
                post.contract.source_digest(rt.historical_projection(frozen))
                == read(post.SESSION / "inputs.json")["actual_inputs_sha256"],
                "C281 origins",
            )
            original, digest = rt.numeric(a.c270)
            rt.bind_c270(a, original, digest)
            _, model = post.contract.placement(a.window, a.placement)
            need(model == original["model_stat"], "placement")
            r.update(status="PREPARED_ONLY", model_launches=0)
        r.update(gates=gates)
    except Exception as exc:
        r.update(
            status="FAIL_PRESERVED",
            failure=f"{type(exc).__name__}: {exc}",
            model_launches=len(list(out.glob("raw/*.launch.json"))),
        )
    r.update(
        mode=a.mode,
        unit=a.unit,
        envelope_s=time.monotonic() - before,
        profile_sha256=sha(__file__),
        protocol_sha256=PROTOCOL,
        denominator_addendum_sha256=DENOMINATORS,
    )
    if r["envelope_s"] > 650:
        r.update(status="FAIL_PRESERVED", failure="650s envelope")
    save(out / "receipt.json", r)
    print(r["status"])
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
