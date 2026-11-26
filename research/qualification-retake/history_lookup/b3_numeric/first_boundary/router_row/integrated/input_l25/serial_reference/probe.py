"""Acquire the serial layer-25 witness with the archived observer and the current original C269."""

import argparse
import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
QUAL = next(p for p in HERE.parents if p.name == "qualification-retake")
CURRENT = QUAL / "packed_nvme_manifest/server_profile/system_driver"
N = run_path(str(CURRENT / "numeric.py"))
R = run_path(str(CURRENT / "review.py"))
SC, PF, need, read, sha, save, prepare, measure = (
    N[k] for k in ("SC", "PF", "need", "read", "sha", "save", "prepare", "measure")
)
sys.path.insert(0, str(HERE.parent))
G = run_path(str(HERE.parent / "grade.py"))
GOLD, OLD = G["integrated"], G["service"]
PREV = G["probes"].load(HERE.parent / "review.py", "previous_l25_review_ar")
META = "750c49aad4b8d48cdfa2dde56182c9aea6edd1fc2fc08e9edabc8a9d2cd4e0cf"
BUILD = "02614356cacecc2261bf7167a7c7079f2f3ad3bf840e9475d430737af9ef6fe9"
ELF = "1858c363a5e668ba9673b9be1295187aa91b0eeb8d01f2137b9d225bbf26be53"
PROTOCOL = "fe52a5c533ab1a96c3c5b773b47e063cf6d32be14e957122af4563ba440bd372"
FAMILY = "3f2e9ffdf46dcb2c68d6f4b515483f56068ef593feff214abab5e27911ff961d"


def prepare_client(a, out):
    need(
        sha(HERE / "protocol.md") == PROTOCOL
        and sha(a.build / "receipt.json") == BUILD
        and sha(HERE.parent / "receipt.json") == META,
        "build and scientific authority",
    )
    b = read(a.build / "receipt.json")
    folder = a.build / "client"
    child = read(folder / "receipt.json")
    need(
        sha(folder / "receipt.json") == b["client_receipt_sha256"]
        and sha(folder / "b3-numeric") == b["client_sha256"] == child["binary_sha256"] == ELF
        and sha(folder / "boundary.cpp") == child["native_source_sha256"]
        and (folder / "boundary.cpp").read_bytes() == G["probes"].render(),
        "original observer and archived source",
    )
    exe = out / "b3-numeric"
    with (folder / "b3-numeric").open("rb") as src, exe.open("xb") as dst:
        shutil.copyfileobj(src, dst)
    exe.chmod(0o500)
    auth = N["Current"](a.static, capture=(exe, ELF))
    env = SC["OLD"]["environment"](auth.verified["search"])
    for name, args in (
        ("list", [SC["OLD"]["LOADER"], "--list", exe]),
        ("relocate", ["/usr/bin/ldd", "-r", exe]),
    ):
        cmd = subprocess.run(args, env=env, capture_output=True, text=True, timeout=25)
        text = cmd.stdout + cmd.stderr
        (out / (name + ".txt")).write_text(text)
        links = SC["OLD"]["interpret"](text)
        need(
            cmd.returncode == 0
            and not re.search("undefined symbol|not found|/stubs/", text)
            and {n: str(p.resolve(strict=True)) for n, p in links.items()}
            == {n: d["file"] for n, d in auth.verified["closure"].items()},
            "R0 providers " + name,
        )
    smoke = subprocess.run(
        [exe, "--self-test"],
        capture_output=True,
        timeout=12,
        env=env | {"CUDA_VISIBLE_DEVICES": ""},
    )
    (out / "self-test.stdout").write_bytes(smoke.stdout)
    (out / "self-test.stderr").write_bytes(smoke.stderr)
    need(
        smoke.returncode == 0 and smoke.stdout == b"PASS_B3_NUMERIC_ROW_PLAN\n",
        "394-site self-test",
    )
    return auth


def archive_controls(archive):
    b = archive / "part-110/tesy-l25-inputs-physical-20261125-r01"
    p = archive / "part-108/tesy-b3-router-integrated-physical-20261125-r01"
    a = archive / "part-102/tesy-b3-first-boundary-physical-20261125-r01"
    c = archive / "part-23/tesy-c270-driver-20261125-r01"
    result = PREV.reopen(b, FAMILY, p, a, c)
    need(
        json.loads(json.dumps(result)) == read(HERE.parent / "receipt.json"),
        "historical B3 contrast",
    )
    return PREV.capture(a, "AR"), PREV.capture(b, "ON")


def compare(cap, gold, ar, b3, sealed, historical_c270):
    base = G["base"]
    norm = OLD.require_arm(cap, "AR", gold, sealed["gold_full_logits_sha256"])
    old = OLD.require_arm(ar, "AR", gold, sealed["gold_full_logits_sha256"])
    need(norm == old and base.bridge(cap, "AR")["bitwise"], "AR prefix, pool, KV and logits")
    logits = {}
    for label in OLD.ROWS:
        v = OLD.logits_grade.compare_rows(OLD.row(ar, label), OLD.row(cap, label))
        need(v["bitwise"] and v["finite"] and v["n_vocab"] == 201088, "serial row " + label)
        logits[label] = v["candidate_sha256"]
    sites = G["probes"].sites()
    now = base.check_arm(cap, "AR", list(GOLD.cuts("AR")) + sites)
    past = base.check_arm(ar, "AR")
    G["paired_subset"](past["files_sha256"], now["files_sha256"])
    independently_stored = GOLD.later_reference(historical_c270)
    _, operands = G["gold_files"](historical_c270)
    independently_stored.update(operands)
    for (pos, layer, name), original in independently_stored.items():
        need(
            sha(original) == now["files_sha256"][f"{pos}.{name}-{layer}.bin"],
            "control operand differs at " + name,
        )
    oldb = base.check_arm(b3, "B3", list(GOLD.cuts("ON")) + sites)
    need(len(now["files_sha256"]) == len(oldb["files_sha256"]) == 1182, "complete new rows")
    pairs = {}
    for pos in (189, 190, 191):
        for il, name, site in sites:
            f = f"{pos}.{name}.bin"
            v = GOLD.diff(cap / "boundary" / f, b3 / "boundary" / f, pos, il, name, site)
            need(
                v["reference_sha256"] == now["files_sha256"][f]
                and v["actual_sha256"] == oldb["files_sha256"][f],
                "paired witness",
            )
            pairs[f] = v
    return dict(
        status="MEASURED_SERIAL_L25_WITNESS",
        serial_prefix=norm["prefix"],
        serial_states=norm["states"],
        serial_logits=logits,
        inherited_serial_payloads=past["payloads"],
        independently_stored_later_rows=len(independently_stored),
        checked_serial_payloads=now["payloads"],
        checked_block_payloads=oldb["payloads"],
        formerly_unpaired_new_rows=25,
        compared_rows=len(pairs),
        pair_sha256_and_differences=pairs,
    )


def family(a, out, r):
    auth = prepare_client(a, out)
    need(
        prepare.git(HERE, "rev-parse", "HEAD") == a.commit
        and not prepare.git(HERE, "status", "--porcelain")
        and re.fullmatch("tesy-ar-l25-[a-z0-9-]+", a.unit),
        "clean revision or unit",
    )
    ar, b3 = archive_controls(a.archive)
    r.update(
        commit=a.commit,
        tree=prepare.git(HERE, "rev-parse", "HEAD^{tree}"),
        unit=a.unit,
        observer_sha256=ELF,
        build_sha256=BUILD,
        protocol_sha256=PROTOCOL,
        source_sha256=sha(Path(__file__)),
        static_sha256=N["STATIC"],
        r0_sha256=R["NUMERIC"],
        block_family_sha256=FAMILY,
        kernel=auth.kernel,
        window_sha256=a.window_sha256,
    )
    c = R["reopen"](a.reference, R["NUMERIC"])
    gold = a.reference / "raw" / (c["unit"] + ".capture")
    locks = SC["OLD"]["locks"](N["REPO"])
    inputs = locks[SC["OLD"]["Q"] + "nvme_r0_gate/inputs/receipt.json"]
    sealed = {k: v for k, v in inputs.items() if k not in ("model_forwards", "status")}
    need(prepare.tree_digest(gold) == sealed["gold"], "C127 complete reference")
    original = locks[SC["OLD"]["C270"]]
    exe, model, ids = map(Path, original["runs"][0]["command"][:3])
    backend = Path(original["backend_root"]).resolve(strict=True)
    need(
        sha(ids) == sealed["ids_sha256"]
        and prepare.git(backend, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()
        == [sealed["backend_commit"], sealed["backend_tree"]]
        and not prepare.git(backend, "status", "--porcelain"),
        "source tree or supplied IDs",
    )
    win = read(a.window / "receipt.json")
    first = json.loads((a.window / "samples.jsonl").read_text().splitlines()[0])["utc"]
    need(
        sha(a.window / "receipt.json") == a.window_sha256
        and sha(a.window / "samples.jsonl") == win["window_sha256"]
        and win["gpu_driver"] == auth.kernel["release"]
        and datetime.fromisoformat(first).timestamp()
        >= int(prepare.git(HERE, "log", "-1", "--format=%ct", "--", "protocol.md")),
        "C55 not prospective",
    )
    prepare.freeze(
        SimpleNamespace(
            window=a.window,
            placement=a.placement,
            envelope="E20_R0",
            measurement_commit=a.commit,
            unit=a.unit,
        ),
        out,
        sealed,
        (exe, model, ids, backend, gold, c["gomp"]),
    )
    raw = out / "raw"
    base = read(out / "protocol.json")
    current = read(a.reference / "current-protocol.json")
    pins = sealed | {
        "capture_sha256": ELF,
        "startup_dso_sha256": current["pinned"]["startup_dso_sha256"],
    }
    cfg = base | dict(
        schema="tesy-current-serial-l25-v1",
        pinned=pins,
        original_sha256=sha(out / "protocol.json"),
        scientific_protocol_sha256=PROTOCOL,
    )
    path = out / "serial-resource.json"
    save(path, cfg)
    env = dict(LD_LIBRARY_PATH=auth.search, LD_DEBUG="libs", LD_DEBUG_OUTPUT=str(raw / "loader"))
    spec = PF["qualified_command"](read(out / "argv.json")["monitor"], Path("/usr/lib64"), env)
    cmd = OLD.derivative_command(spec, exe.resolve(strict=True), auth.exe, gold, "AR", a.unit, path)
    save(out / "serial-argv.json", cmd)
    r["monitor_provider"] = N["AU"]["Authority"].monitor_proof(auth.monitor)
    expected = {"TESY_CPU_WAVE_SKIP_PARKED": "1"} | env
    policy = read(out / "resource-policy.json")

    def check_age(moment):
        age = (moment - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
        need(0 <= age < 3600, "C55 age")
        return age

    check_age(datetime.now(UTC))
    ident, count, seen, wall = PF["guarded_run"](cmd, out, a.unit, auth, measure, N["run_bounded"])
    m = read(raw / (a.unit + ".json"))
    launch = read(raw / (a.unit + ".launch.json"))
    need(
        m["process_identity"] == ident == launch["process_identity"]
        and m["command"] == cmd[-6:]
        and m["limits"]["resource_protocol_sha256"]
        == launch["resource_protocol_sha256"]
        == sha(path)
        and measure.file_bytes(raw) <= 128 << 20
        and "TESY_B3_ROUTER_ROW" not in expected,
        "runtime identity or bounds",
    )
    PF["check_native_manifest"](m, cfg, pins, expected, measure)
    compact = G["probes"].load(
        QUAL / "nvme_r0_gate/qualified_profile/compact.py", "check_serial_inventory"
    )
    inv = compact.validate_inventory(out, a.unit, {"native_explicit_env": expected}, launch)
    audit = auth.audit(raw, ident["pid"])
    need({Path(n).name for n in seen} <= audit["initialized"].keys(), "unreconciled live mapping")
    numeric = compare(
        raw / (a.unit + ".capture"),
        gold,
        ar,
        b3,
        sealed,
        a.archive / "part-23/tesy-c270-driver-20261125-r01",
    )
    save(out / "numeric.json", numeric)
    r.update(
        status=numeric["status"],
        numerical_sha256=sha(out / "numeric.json"),
        live_samples=count,
        loader=audit,
        c118=inv,
        c55_age_at_spawn_s=check_age(
            datetime.fromisoformat(launch["start_inventory"]["popen_invoked_utc"])
        ),
        scope_s=wall,
        model_s=m["elapsed_s"],
        maxima=m["maxima"],
        scope_cleanup=True,
        model_sha256=c["model_sha256"],
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for label in (
        "static",
        "build",
        "reference",
        "archive",
        "window",
        "placement",
        "new-output-dir",
    ):
        p.add_argument("--" + label, type=Path, required=True)
    for label in ("unit", "commit", "window-sha256"):
        p.add_argument("--" + label, required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    r = dict(status="FAIL_PRESERVED", generation_requests=0)

    def timeout(*_):
        raise TimeoutError("ten-minute serial observation")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(600)
    try:
        with (Path("/run/user") / str(os.getuid()) / "tesy-c110-callback.lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            family(a, out, r)
    except Exception as exc:
        r["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        signal.alarm(0)
    r["model_starts"] = len(list(out.glob("raw/*.launch.json")))
    r["raw_sha256"] = {
        str(f.relative_to(out)): sha(f) for f in sorted(out.rglob("*")) if f.is_file()
    }
    save(out / "receipt.json", r)
    print(r["status"], r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
