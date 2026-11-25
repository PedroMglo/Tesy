"""Selected C292 parity for the recompiled C291 control and production pack observer."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[4]
CAPTURE = QUAL / "packed_nvme_manifest/capture_numeric"
sys.path.insert(0, str(CAPTURE))
import live  # noqa: E402

mod = live.linkage.load_module
base = mod(CAPTURE / "profile.py", "pack_previous_numeric_profile")
grade = mod(CAPTURE / "grade.py", "pack_previous_numeric_grade")
pfj = mod(QUAL / "phase_fd/integrated/analyse.py", "pack_numeric_rows")
sys.path.insert(0, str(HERE.parent / "natural_trace"))
from jobs import audit_jobs  # noqa: E402

save, need, read, sha = base.save, live.need, live.read, live.sha
MODES = ("control_off", "overlay_off", "overlay_on")
METHOD = "cf6eff514e784a972efd183f23f8d154255a7b401cb8090d097e837f91d22c1c"
BUILD = "cfd616fda7fcdac7aaf6774f9b6d2aac7ea5186a5629fa33eb1bff58a00b34c8"
FAMILY = "f7a5f270e427b8b9390b17ae1a49b2d154a57a822b9afc0ab1c1039f0641b9c7"
LIBS = {
    "original": live.static.C291,
    "control": "772740127a1227afae0b0325d0b186f35e1c7e428d6929181019bb8c455b6b25",
    "overlay": "9cfa88074e7ca6fa0723f9529aa72b70cea82f2a4bcca53e993733b0f393a0c5",
}
MONITOR = CAPTURE.parent / "server_profile/conversation/transport_profile.py"
FILE, TRIGGER = "TESY_PHASE_FD_FILE", "TESY_PHASE_FD_TRIGGER"


def original(folder, gold):
    family = grade.read(folder / "receipt.json", FAMILY)
    need(family["status"] == "PASS_SELECTED_C292_NVME_PAIR", "original C292 pair")
    arm = grade.read(folder / "ON/receipt.json", family["arms"][1]["receipt_sha256"])
    captured = folder / "ON/raw" / (arm["unit"] + ".capture")
    grade.regular_files(captured)
    tree = grade.tree_digest(captured)
    need(
        arm["status"] == "PASS_C292_ON"
        and arm["pack"]["positive_samples"] > 0
        and arm["loader"]["initialized_sha256"]["libllama.so.0.0.9884"] == LIBS["original"]
        and tree == arm["numerical"]["c292"]["capture"] == grade.tree_digest(gold),
        "original pack capture or independent C270 changed",
    )
    return tree


def validate_maps(old, observed, selected, digest):
    name = live.static.SONAME
    need(
        len(old) == len(observed) == 18
        and old.keys() == observed.keys()
        and old[name]["sha256"] == LIBS["original"]
        and all(observed[k] == old[k] for k in old if k != name)
        and observed[name] == {"file": str(selected), "sha256": digest},
        "C292 provider identity",
    )


class NumericalAuthority(live.CaptureAuthority):
    def __init__(self, a, arm, journal):
        super().__init__(a, "ON")
        b = grade.read(a.build_dir / "receipt.json", BUILD)
        key = "control" if arm == "control_off" else "candidate"
        overlay = key == "candidate"
        digest = LIBS["overlay" if overlay else "control"]
        need(
            b["status"] == "PASS_C291_PACK_PFJ_DSO_STATIC_C281"
            and b["build_variant"] == "current_compiler_control"
            and b["static_preflight_sha256"] == live.static.PREFLIGHT
            and b["c292_closure_sha256"] == live.CLOSURE
            and b["patch_sha256"] == sha(HERE.parent / "observer.patch")
            and b["original_sha256"] == LIBS["original"]
            and b[key + "_sha256"] == digest,
            "unqualified production build",
        )
        self.image = (a.build_dir / b[key + "_file"]).resolve(strict=True)
        self.digest = sha(self.image)
        self.journal = journal if arm == "overlay_on" else None
        name = live.static.SONAME
        baseline = grade.read(a.closure_dir / "receipt.json", live.CLOSURE)["startup"]
        resolved = b["capture_startup" if overlay else "control_capture_startup"]
        validate_maps(baseline, resolved, self.image, digest)
        alias = (a.build_dir / ("libs" if overlay else "control-libs")).resolve(strict=True)
        self.new_alias, self.new_bindings = alias, {name: str(self.image)}
        live.aliases(alias, self.new_bindings)
        search = [str(alias), *self.arm["native_search"][1:]]
        listed = self.static.interpret(
            self.static.command(
                [self.static.LOADER, "--list", self.exe], self.static.environment(search)
            )
        )
        links = {n: [str(p), str(p.resolve(strict=True))] for n, p in listed.items()}
        need(
            self.digest == digest
            and links.keys() == resolved.keys()
            and all(links[k] == v for k, v in self.links.items() if k != name)
            and links[name] == [str(alias / name), str(self.image)]
            and all(v[1] == resolved[k]["file"] for k, v in links.items()),
            "effective numerical loader selection",
        )
        self.files[str(self.image)] = live.identity(self.image) | {"sha256": digest}
        self.links = links
        self.arm = self.arm | dict(native_search=search)
        self.native_search = ":".join(search)
        self.initial = {r[1] for r in links.values()}
        self.allowed = self.initial | set(map(str, self.drivers.values()))
        self.vma_keys = {p: live.reference_key(p, self.files[p]) for p in self.allowed}
        self.recheck()

    def live(self, pid):
        if not self.env_checked:
            values = (Path("/proc", str(pid), "environ")).read_bytes().split(b"\0")
            phase = [
                x for x in values if x.startswith((FILE.encode() + b"=", TRIGGER.encode() + b"="))
            ]
            need(
                phase == ([os.fsencode(f"{FILE}={self.journal}")] if self.journal else []),
                "journal environment at live PID",
            )
        return super().live(pid)


def inspect_journal(path, enabled, pack, model):
    if not enabled:
        need(not path.exists() and not path.is_symlink(), "unexpected journal in OFF")
        return {"enabled": False}
    need(
        path.is_file() and not path.is_symlink() and path.stat().st_mode & 0o777 == 0o600,
        "private journal",
    )
    rows, header = pfj.read_journal(path)
    starts = [r for r in rows if r.kind == 1]
    ends = [r for r in rows if r.kind == 2]
    tiles = [r for r in rows if r.kind == 3]
    returns = [r for r in rows if r.kind == 4]
    expected = [(1, 189, 0, 188)] + [(k, 1, 187 + k, 187 + k) for k in range(2, 34)]
    need(
        [(r.call, r.a, r.b, r.c) for r in starts] == expected
        and [(r.call, r.a) for r in ends] == [(k, 0) for k in range(1, 34)],
        "189+32 call geometry or return",
    )
    expected_tiles = [
        (1, i + 1, n, 32 * i, 32 * i + n - 1) for i, n in enumerate((32,) * 5 + (29,))
    ]
    expected_tiles += [(k, 1, 1, 187 + k, 187 + k) for k in range(2, 34)]
    need(
        [(r.call, r.tile, r.a, r.b, r.c) for r in tiles] == expected_tiles
        and [(r.call, r.tile, r.a) for r in returns] == [(k, t, 0) for k, t, *_ in expected_tiles]
        and Counter(r.worker for r in rows if r.kind == 24) == Counter(range(4)),
        "tile or worker lifecycle",
    )
    out = audit_jobs(rows, pack, model)
    need(
        out["status"] == "COMPLETE" and out["eligible_clean_run"], "incomplete or failed pack jobs"
    )
    return {
        "enabled": True,
        **header,
        "counts": dict(out["counts"]),
        "calls": len(starts),
        "tiles": len(tiles),
        "job_status": out["status"],
        "fds": out["fds"],
    }


def c55_age(policy, now):
    elapsed = (now - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
    need(0 <= elapsed < 55 * 60, "C55 expired")
    return elapsed


def arm(a, out, mode, gold, original_tree, r):
    unit = a.unit + "-" + mode.replace("_", "-")
    raw = out / "raw"
    journal = raw / "phase.pfj1"
    ctl = NumericalAuthority(a, mode, journal)
    prep = argparse.Namespace(**(vars(a) | dict(unit=unit, execute=False)))
    result = base.up.prepare_campaign(prep, out)
    need(result["status"] == "PREPARED_ONLY", "initial independent preflight")
    baseline, protocol = read(out / "qualified-protocol.json"), read(out / "protocol.json")
    pinned = protocol["pinned"]
    source_root = Path(base.prepare.load(base.prepare.BASE)["backend_root"])
    name = ctl.image.name
    need(
        pinned["backend_commit"] == live.linkage.WORKER
        and base.prepare.git(ctl.backend, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()
        == [live.static.PIN, live.static.TREE]
        and not base.prepare.git(ctl.backend, "status", "--porcelain")
        and protocol["model_stat"] == ctl.data_stats["model"],
        "pinned C291 and model",
    )
    for key in ("numerical_dso_sha256", "startup_dso_sha256"):
        need(pinned[key][name] == live.static.C269, "original numerical provider")
        pinned[key][name] = ctl.digest
    pinned.update(
        backend_commit=live.static.PIN,
        backend_tree=live.static.TREE,
        capture_sha256=live.static.CAPTURE,
    )
    policy = read(out / "resource-policy.json")
    policy_sha = sha(out / "resource-policy.json")
    protocol.update(
        schema="tesy-c292-private-pack-pfj-numeric-v1",
        build_sha256=BUILD,
        method_sha256=METHOD,
        runner_sha256=sha(MONITOR),
        mode=mode,
    )
    save(out / "resource-store.json", protocol)
    spec = base.command(baseline["monitor"], ctl, out, "ON", source_root)
    base.replace_once(spec, "LimitFSIZE=8388608", "LimitFSIZE=33554432")
    at = spec.index(str(base.PFJ / "monitor.py"))
    spec[at : at + 1] = [
        str(MONITOR),
        "--c55-launch-policy",
        str(out / "resource-policy.json"),
        policy_sha,
    ]
    expected = {"TESY_CPU_WAVE_SKIP_PARKED": "1", live.STORE_ENV: str(ctl.data_paths["manifest"])}
    expected.update(ctl.child_env(raw / "loader"))
    if ctl.journal:
        i = spec.index("--", spec.index("--env"))
        spec[i:i] = ["--env", FILE + "=" + str(journal)]
        expected[FILE] = str(journal)
    capture = raw / (unit + ".capture")
    need(
        not os.path.lexists(journal) and not os.path.lexists(capture) and Path(spec[-3]) == capture,
        "exclusive arm outputs",
    )
    save(
        out / "argv-observer.json",
        dict(
            argv=spec,
            explicit_env=expected,
            mode=mode,
            model_stat=ctl.data_stats["model"],
            pack_stat=ctl.data_stats["pack"],
            pinned=LIBS,
            resource_sha256=sha(out / "resource-store.json"),
        ),
    )
    r.update(
        unit=unit,
        image_sha256=ctl.digest,
        journal_enabled=bool(ctl.journal),
        contract_sha256=sha(out / "argv-observer.json"),
        build_receipt_sha256=BUILD,
    )
    if not a.execute:
        r["status"] = "PREPARED_ONLY"
        return
    c55_age(policy, datetime.now(UTC))
    r["monitor_provider"] = ctl.monitor_proof()
    ident, n, seen, wall = base.up.guarded_run(
        spec, out, unit, ctl, base.measure, live.linkage.run_bounded
    )
    postflight(
        ctl,
        out,
        out,
        unit,
        expected,
        gold,
        original_tree,
        r,
        ident,
        n,
        seen,
        wall,
        ctl.fd_evidence(),
    )


def postflight(
    ctl, out, review, unit, expected, gold, original_tree, r, ident, n, seen, wall, fd_evidence
):
    raw = out / "raw"
    capture = raw / (unit + ".capture")
    journal = raw / "phase.pfj1"
    protocol = read(out / "resource-store.json")
    policy = read(out / "resource-policy.json")
    baseline = read(out / "qualified-protocol.json")
    launch = read(raw / (unit + ".launch.json"))
    m = read(raw / (unit + ".json"))
    need(
        ident == m["process_identity"] == launch["process_identity"]
        and launch["resource_protocol_sha256"]
        == m["limits"]["resource_protocol_sha256"]
        == sha(out / "resource-store.json"),
        "runtime scope/resource",
    )
    actual = m["relevant_environment"]
    need(
        m["explicit_env"] == expected
        and all(actual.get(k) == expected.get(k) for k in (FILE, TRIGGER, live.STORE_ENV)),
        "actual scope environment",
    )
    normalized = dict(m)
    normalized["explicit_env"] = {k: v for k, v in expected.items() if k != FILE}
    base.validate_monitor(normalized, normalized["explicit_env"], protocol)
    loader = ctl.audit(raw / "loader", ident["pid"])
    need(
        len(ctl.initial) == 18
        and ctl.initial <= set(seen)
        and all(
            loader["initialized_sha256"].get(Path(path).name) == ctl.files[path]["sha256"]
            for path in ctl.initial
        )
        and loader["initialized_sha256"][ctl.image.name] == ctl.digest
        and {Path(v).name for v in seen} <= loader["initialized_sha256"].keys(),
        "observed numerical loader",
    )
    r.update(
        c118=base.compact.validate_inventory(out, unit, {"native_explicit_env": expected}, launch),
        c55_age_at_spawn_s=c55_age(
            policy, datetime.fromisoformat(launch["start_inventory"]["popen_invoked_utc"])
        ),
        loader=loader,
        pack=fd_evidence,
        maxima=m["maxima"],
        live_samples=n,
        cleanup=True,
        scoped_wall_s=wall,
        model_s=m["elapsed_s"],
        monitor_sha256=sha(raw / (unit + ".json")),
        launch_sha256=sha(raw / (unit + ".launch.json")),
    )
    need(
        base.measure.file_bytes(raw) <= 128 << 20
        and all(p.stat().st_size <= 8 << 20 for p in grade.regular_files(capture)),
        "output caps",
    )
    r["journal"] = inspect_journal(
        journal, bool(ctl.journal), ctl.data_stats["pack"], ctl.data_stats["model"]
    )
    check_cmd = list(baseline["check"])
    base.replace_once(check_cmd, str(out / "selected.json"), str(review / "selected.json"))
    with (review / "c127-check.log").open("xb") as log:
        subprocess.run(check_cmd, stdout=log, stderr=subprocess.STDOUT, timeout=45, check=True)
    c127 = read(review / "selected.json")
    base.measure.check_gate(c127)
    numerics = grade.check_arm(capture, raw / (unit + ".stdout"), gold, c127)
    need(
        numerics["status"] == "PASS_C292_ARM_NUMERICS"
        and numerics["c292"]["capture"] == original_tree,
        "C127/C270/original-C291 gate",
    )
    save(review / "numerical.json", numerics)
    r.update(
        status=numerics["status"],
        capture_tree=numerics["c292"]["capture"],
        numerical_sha256=sha(review / "numerical.json"),
        c127_sha256=sha(review / "selected.json"),
    )


FAILED = "a6bd01e79fef679a739195efbd102a0b40861d017f0fa063dac904fa5f72a306"
LIVE_CONTROL = "5b113a33e9f6d4f16797ac6fe29aa2ff05593a6c621039ada27494932e737177"
R01_MONITOR = "c68b7974757e20aef54bb374285f388adf4d13aad74dda2d0e76e01bf3ebdfb4"


def reopen_control(a, dest, gold, tree, row):
    terminal = grade.read(a.failed_family / "receipt.json", FAILED)
    proof = grade.read(a.control_fds / "receipt.json", LIVE_CONTROL)
    pdata = a.failed_family / "control_off"
    physical = grade.read(pdata / "receipt.json", terminal["arms"]["control_off"]["receipt_sha256"])
    unit = physical["unit"]
    raw = pdata / "raw"
    contract = grade.read(pdata / "argv-observer.json", physical["contract_sha256"])
    launch = grade.read(raw / (unit + ".launch.json"), proof["launch_sha256"])
    end = grade.read(raw / (unit + ".json"), R01_MONITOR)
    ident = proof["process_identity"]
    need(
        terminal["status"] == "FAIL_PRESERVED"
        and terminal["model_launch_receipts"] == 1
        and physical["reason"] == "KeyError: 'startup_count'"
        and terminal["unexecuted_arms"] == ["overlay_off", "overlay_on"]
        and proof["status"] == "PASS_LIVE_CONTROL_OFF_FD"
        and proof["digest"] == physical["image_sha256"] == LIBS["control"]
        and proof["source"] == "ff7543204a687fdaa1aa52ba354d6f5cdc7f91a8c86f1a201bba8775360c3fe6"
        and ident == end["process_identity"] == launch["process_identity"]
        and end["returncode"] == 0
        and end["stop_reason"] is None
        and not Path("/proc", str(ident["pid"])).exists()
        and base.up.scope_active(unit) in {"inactive", "unknown"}
        and "status=0/SUCCESS" in (pdata / "scope.log").read_text()
        and sha(pdata / "resource-store.json") == contract["resource_sha256"]
        and sha(pdata / "resource-policy.json") == sha(a.window / "resource-policy.json"),
        "failed review versus physical control authority",
    )
    ctl = NumericalAuthority(a, "control_off", raw / "phase.pfj1")
    samples_path = a.control_fds / "samples.jsonl"
    need(sha(samples_path) == proof["sample_sha256"], "control FD samples")
    samples = [json.loads(line) for line in samples_path.read_bytes().splitlines()]
    fd = proof["pack"]
    need(
        len(samples) == proof["samples"] == fd["positive_samples"] == 4
        and len(fd["fd_and_flags"]) == 1
        and fd["fd_and_flags"][0][1] & os.O_DIRECT
        and fd["fd_and_flags"][0][1] & os.O_ACCMODE == os.O_RDONLY
        and all(
            s["pid"] == ident["pid"]
            and s["pack"] == fd["fd_and_flags"]
            and s["model_stat"] == ctl.data_stats["model"] == contract["model_stat"]
            and s["pack_stat"] == ctl.data_stats["pack"] == contract["pack_stat"]
            and s["environ_verified"]
            and set(s["mapped"]) <= ctl.allowed
            for s in samples
        ),
        "reopened live FD samples",
    )
    seen = set().union(*(s["mapped"] for s in samples))
    need(
        seen == set(proof["observed"]) and ctl.initial == set(proof["startup"]),
        "original live VMA census",
    )
    row.update(
        unit=unit,
        journal_enabled=False,
        image_sha256=ctl.digest,
        build_receipt_sha256=BUILD,
        contract_sha256=physical["contract_sha256"],
        r01_family_sha256=FAILED,
        live_fd_sha256=LIVE_CONTROL,
        raw_at=str(pdata),
        monitor_provider=physical["monitor_provider"],
        reused_measured_control=True,
    )
    postflight(
        ctl,
        pdata,
        dest,
        unit,
        contract["explicit_env"],
        gold,
        tree,
        row,
        ident,
        len(samples),
        seen,
        None,
        fd,
    )


def campaign(a, out, r):
    need(
        sha(HERE / "protocol.md") == METHOD
        and a.build_sha256 == BUILD
        and sha(a.build_dir / "receipt.json") == BUILD,
        "method/build pin",
    )
    a.checkout, a.preflight_sha256 = live.REPO, live.static.PREFLIGHT
    need(
        base.prepare.git(live.REPO, "rev-parse", "HEAD") == a.measurement_commit
        and not base.prepare.git(live.REPO, "status", "--porcelain"),
        "measurement freeze",
    )
    gold = grade.reference(a.r0_dir)
    tree = original(a.original_family, gold)
    r.update(
        independent_reference={
            "c270_receipt_sha256": grade.R0,
            "c291_family_sha256": FAMILY,
            "capture_tree": tree,
        },
        revalidated_prior_launch_receipts=1,
        boundary_scope="C127_selected_189_plus_32",
        libraries=LIBS,
        build_receipt_sha256=BUILD,
        protocol_sha256=METHOD,
        c55_sha256=a.window_sha256,
    )
    for mode in MODES:
        dest = out / mode
        dest.mkdir()
        row = dict(status="FAIL_PRESERVED", mode=mode)
        try:
            if mode == "control_off":
                reopen_control(a, dest, gold, tree, row)
            else:
                arm(a, dest, mode, gold, tree, row)
        except Exception as exc:
            row["reason"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            row["model_launch_receipts"] = len(list((dest / "raw").glob("*.launch.json")))
            save(dest / "receipt.json", row)
            selected = ("status", "image_sha256", "journal_enabled", "capture_tree")
            r["arms"][mode] = {k: row[k] for k in selected if k in row}
            r["arms"][mode]["receipt_sha256"] = sha(dest / "receipt.json")
            r["model_launch_receipts"] += row["model_launch_receipts"]
    if a.execute:
        need(
            r["model_launch_receipts"] == 2
            and all(x["capture_tree"] == tree for x in r["arms"].values()),
            "three independent captures",
        )
    r["status"] = "PASS_C292_PACK_OBSERVER_NUMERIC" if a.execute else "PREPARED_ONLY"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in (
        "build-dir",
        "original-family",
        "failed-family",
        "control-fds",
        "closure-dir",
        "preflight-dir",
        "r0-dir",
        "derived-dir",
        "constructor-receipt",
        "window",
        "placement",
        "new-output-dir",
    ):
        p.add_argument("--" + arg, type=Path, required=True)
    for arg in ("build-sha256", "window-sha256", "measurement-commit", "unit"):
        p.add_argument("--" + arg, required=True)
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    r = dict(status="FAIL_PRESERVED", arms={}, model_launch_receipts=0, commit=a.measurement_commit)

    def expired(*_):
        raise TimeoutError("1080 s family budget")

    start = time.monotonic()
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(1080)
    try:
        campaign(a, out, r)
    except Exception as exc:
        r["reason"] = f"{type(exc).__name__}: {exc}"
    finally:
        signal.alarm(0)
        r.update(
            elapsed_s=time.monotonic() - start,
            unexecuted_arms=[m for m in MODES if m not in r["arms"]],
        )
        save(out / "receipt.json", r)
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
