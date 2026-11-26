"""Compare AR and B3 at the input to the output projection under one driver and graph library."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import signal
import struct
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
B = run_path(str(HERE / "build.py"))
S = B["S"]
N, PF, SC, R, G, OLD, need, read, sha, save, prepare, measure = (
    S[k]
    for k in ("N", "PF", "SC", "R", "G", "OLD", "need", "read", "sha", "save", "prepare", "measure")
)
BUILD = "e2a38bb6ca24e284d2ba3d08a0966dd5cfec146ca72a92cba1801e277beead64"
SERIAL = "6cd62fa18eb95c90cd0201b97b05c38b1279570e8b7d465579f0167aa1048935"
NAME = "__fattn__-25"
SITE = S["GOLD"].SITES[0]._replace(name="__fattn__", dims=(64, 64), ops=("FLASH_ATTN_EXT",))
MONITOR = S["QUAL"] / "phase_fd/integrated/profile/monitor.py"


def mask(path):
    data = path.read_bytes()
    need(2 <= len(data) <= 16384 and not len(data) % 2, "mask byte count")
    words = struct.unpack(f"<{len(data) // 2}H", data)
    need(all(w in (0, 0xFC00) for w in words), "unexpected mask bits")
    return words


def grade_arm(cap, mode, gold, previous, pins):
    prev = OLD.require_arm(previous, mode, gold, pins["gold_full_logits_sha256"])
    observed = OLD.require_arm(cap, mode, gold, pins["gold_full_logits_sha256"])
    need(observed == prev, mode + " controls for prefix, snapshots and logits")
    vectors = {}
    for key in OLD.ROWS:
        result = OLD.logits_grade.compare_rows(OLD.row(previous, key), OLD.row(cap, key))
        need(
            result["bitwise"] and result["finite"] and result["n_vocab"] == 201088,
            "same-mode logits " + key,
        )
        vectors[key] = result["candidate_sha256"]
    cuts = list(S["GOLD"].cuts("AR" if mode == "AR" else "ON")) + G["probes"].sites()
    before = G["base"].check_arm(previous, mode, cuts)
    after = G["base"].check_arm(cap, mode, cuts + [(25, NAME, SITE)])
    G["paired_subset"](before["files_sha256"], after["files_sha256"])
    need(before["payloads"] == 1182 and after["payloads"] == 1185, "arm coverage")
    masks = {}
    for pos in (189, 190, 191):
        file = cap / f"mask-25-{pos}.f16"
        words = mask(file)
        masks[str(pos)] = dict(
            sha256=sha(file), cells=len(words), visible=words.count(0), masked=words.count(0xFC00)
        )
    return dict(
        status="PASS_SAME_MODE_WITNESS",
        serial_or_block=mode,
        masks=masks,
        common_payloads=before["payloads"],
        observed_payloads=after["payloads"],
        states=observed["states"],
        logits_sha256=vectors,
        geometry_sha256=after["geometry_sha256"],
    )


def grade_pair(ar, b3):
    results = {}
    for pos in (189, 190, 191):
        fields = {}
        for name, site in (
            (NAME, SITE),
            ("attn_out-25", next(s for s in S["GOLD"].SITES if s.name == "attn_out")),
        ):
            leaf = f"{pos}.{name}.bin"
            fields[name] = S["GOLD"].diff(
                ar / "boundary" / leaf, b3 / "boundary" / leaf, pos, 25, name, site
            )
        af, bf = (x / f"mask-25-{pos}.f16" for x in (ar, b3))
        left, right = mask(af), mask(bf)
        overlap = min(len(left), len(right))
        unmatched = left[overlap:] + right[overlap:]
        changes = [i for i, (a, b) in enumerate(zip(left, right, strict=False)) if a != b]
        need(
            fields[NAME]["words"] == 4096 and fields["attn_out-25"]["words"] == 2880,
            "attention or projection geometry",
        )
        fields["mask"] = dict(
            AR_cells=len(left),
            B3_cells=len(right),
            AR_visible=left.count(0),
            B3_visible=right.count(0),
            AR_sha256=sha(af),
            B3_sha256=sha(bf),
            common_cells_different=len(changes),
            first_different_cell=next(iter(changes), None),
            trailing_unmatched_visible=unmatched.count(0),
            bitwise_identical=left == right,
        )
        upstream = fields[NAME]["changed_words"]
        downstream = fields["attn_out-25"]["changed_words"]
        fields["diagnosis"] = (
            "DIFFERENT_BEFORE_OUTPUT_PROJECTION"
            if upstream
            else "DIFFERENT_AT_OUTPUT_PROJECTION_OR_BIAS"
            if downstream
            else "SAME_AT_BOTH_CUTS"
        )
        results[str(pos)] = fields
    return dict(status="MEASURED_SAME_DRIVER_ATTENTION_CUT", positions=results)


def run_arm(a, mode, directory, auth, original, pins, control, previous, child_ref):
    directory.mkdir()
    exe, model, ids = map(Path, original["runs"][0]["command"][:3])
    backend = Path(original["backend_root"]).resolve(strict=True)
    need(
        sha(ids) == pins["ids_sha256"]
        and prepare.git(backend, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()
        == [pins["backend_commit"], pins["backend_tree"]]
        and not prepare.git(backend, "status", "--porcelain"),
        "input and clean source",
    )
    unit = a.unit + "-" + mode.lower()
    req = SimpleNamespace(
        window=a.window,
        placement=a.placement,
        envelope="E20_R0",
        measurement_commit=a.commit,
        unit=unit,
    )
    gold = a.reference / "raw" / (control["unit"] + ".capture")
    prepare.freeze(req, directory, pins, (exe, model, ids, backend, gold, control["gomp"]))
    raw = directory / "raw"
    base = read(directory / "protocol.json")
    sealed = dict(pins)
    library = Path(auth.verified["closure"][SC["SONAME"]]["file"]).name
    need(pins["numerical_dso_sha256"][library] != B["IMAGE"], "missing independent baseline")
    sealed.update(
        capture_sha256=auth.arm["executable_sha256"],
        numerical_dso_sha256=pins["numerical_dso_sha256"] | {library: B["IMAGE"]},
        startup_dso_sha256={
            Path(v["file"]).name: v["sha256"]
            for k, v in auth.verified["closure"].items()
            if k != SC["OLD"]["LOADER"].name
        },
    )
    protocol = base | dict(
        schema="tesy-current-l25-flash-v1",
        pinned=sealed,
        runner_sha256=sha(MONITOR),
        original_sha256=sha(directory / "protocol.json"),
        scientific_protocol_sha256=B["METHOD"],
    )
    config = directory / "attention-resource.json"
    save(config, protocol)
    loader = dict(LD_LIBRARY_PATH=auth.search, LD_DEBUG="libs", LD_DEBUG_OUTPUT=str(raw / "loader"))
    env = {"TESY_CPU_WAVE_SKIP_PARKED": "1"} | loader | {B["ON"]: "1"}
    orig = PF["qualified_command"](
        read(directory / "argv.json")["monitor"], Path("/usr/lib64"), loader
    )
    cmd = OLD.derivative_command(
        orig, exe.resolve(strict=True), auth.exe, child_ref, mode, unit, config
    )
    runner = str(N["REPO"] / "tools/run_bounded.py")
    need(cmd.count(runner) == 1, "frozen resource monitor")
    cmd[cmd.index(runner)] = str(MONITOR)
    idx = cmd.index("--", cmd.index("--env"))
    cmd[idx:idx] = ["--env", B["ON"] + "=1"]
    save(directory / "attention-argv.json", cmd)
    policy = read(directory / "resource-policy.json")

    def age(at):
        seconds = (at - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
        need(0 <= seconds < 3600, "C55 age")
        return seconds

    age(datetime.now(UTC))
    mon = N["AU"]["Authority"].monitor_proof(auth.monitor)
    ident, n, seen, wall = PF["guarded_run"](cmd, directory, unit, auth, measure, N["run_bounded"])
    launch, m = (read(raw / (unit + suffix)) for suffix in (".launch.json", ".json"))
    need(
        m["process_identity"] == launch["process_identity"] == ident
        and m["command"] == cmd[-6:]
        and sha(config)
        == m["limits"]["resource_protocol_sha256"]
        == launch["resource_protocol_sha256"]
        and measure.file_bytes(raw) <= 128 << 20,
        "resource identity",
    )
    need(
        m["explicit_env"] == env
        and all(
            m["relevant_environment"].get(k) == v
            for k, v in env.items()
            if k not in ("LD_DEBUG", "LD_DEBUG_OUTPUT")
        ),
        "live treatment",
    )
    standard = {"TESY_CPU_WAVE_SKIP_PARKED": "1"} | loader
    PF["check_native_manifest"](dict(m, explicit_env=standard), protocol, sealed, standard, measure)
    compact = G["probes"].load(
        S["QUAL"] / "nvme_r0_gate/qualified_profile/compact.py", "attn_inventory"
    )
    inv = compact.validate_inventory(directory, unit, {"native_explicit_env": env}, launch)
    audit = auth.audit(raw, ident["pid"])
    need({Path(x).name for x in seen} <= audit["initialized"].keys(), "runtime providers")
    cap = raw / (unit + ".capture")
    verified = grade_arm(cap, mode, gold, previous, pins)
    save(directory / "same-mode.json", verified)
    return cap, dict(
        status=verified["status"],
        same_mode_sha256=sha(directory / "same-mode.json"),
        monitor_provider=mon,
        live_samples=n,
        scope_s=wall,
        model_s=m["elapsed_s"],
        loader=audit,
        maxima=m["maxima"],
        c118=inv,
        scope_cleanup=True,
        c55_age_s=age(datetime.fromisoformat(launch["start_inventory"]["popen_invoked_utc"])),
    )


def run(a, out, r):
    need(
        sha(a.build / "receipt.json") == BUILD
        and sha(HERE / "protocol.md") == B["METHOD"]
        and prepare.git(HERE, "rev-parse", "HEAD") == a.commit
        and not prepare.git(HERE, "status", "--porcelain")
        and re.fullmatch("tesy-current-attn-[a-z0-9-]+", a.unit),
        "campaign authority",
    )
    build = read(a.build / "receipt.json")
    need(
        build["status"] == "GO_CURRENT_ATTENTION_PAIR"
        and sha(a.build / "boundary.cpp")
        == build["source_sha256"]
        == hashlib.sha256(B["render"]()).hexdigest(),
        "added cut",
    )
    auth = B["Authority"](a.static, a.build, build["elf_sha256"])
    need(auth.verified["closure"] == build["current_providers"], "current closure")
    ctrl = R["reopen"](a.reference, R["NUMERIC"])
    serial = R["reopen"](a.serial, SERIAL)
    _, b3 = S["archive_controls"](a.archive)
    prior_ar = a.serial / "raw" / (serial["unit"] + ".capture")
    src = SC["OLD"]["locks"](N["REPO"])
    hist = src[SC["OLD"]["C270"]]
    pins = {
        k: v
        for k, v in src[SC["OLD"]["Q"] + "nvme_r0_gate/inputs/receipt.json"].items()
        if k not in ("model_forwards", "status")
    }
    gold = a.reference / "raw" / (ctrl["unit"] + ".capture")
    win = read(a.window / "receipt.json")
    first = json.loads((a.window / "samples.jsonl").read_text().splitlines()[0])["utc"]
    need(
        prepare.tree_digest(gold) == pins["gold"]
        and win["gpu_driver"] == auth.kernel["release"]
        and sha(a.window / "receipt.json") == a.window_sha256
        and sha(a.window / "samples.jsonl") == win["window_sha256"]
        and datetime.fromisoformat(first).timestamp()
        >= int(prepare.git(HERE, "log", "-1", "--format=%ct", "--", "protocol.md")),
        "reference or prospective window",
    )
    r.update(
        commit=a.commit,
        tree=prepare.git(HERE, "rev-parse", "HEAD^{tree}"),
        unit=a.unit,
        driver=auth.kernel,
        build_sha256=BUILD,
        protocol_sha256=B["METHOD"],
        source_sha256=sha(Path(__file__)),
        r0_sha256=R["NUMERIC"],
        serial_sha256=SERIAL,
        previous_block_sha256=S["FAMILY"],
        window_sha256=a.window_sha256,
        arms={},
    )
    caps = {}
    for mode, previous in (("AR", prior_ar), ("B3", b3)):
        r["last_arm"] = mode
        caps[mode], r["arms"][mode] = run_arm(
            a, mode, out / mode, auth, hist, pins, ctrl, previous, caps.get("AR", gold)
        )
    result = grade_pair(caps["AR"], caps["B3"])
    save(out / "pair.json", result)
    r.update(status=result["status"], pair_sha256=sha(out / "pair.json"))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for field in (
        "static",
        "build",
        "reference",
        "serial",
        "archive",
        "window",
        "placement",
        "new-output-dir",
    ):
        cli.add_argument("--" + field, required=True, type=Path)
    for field in ("commit", "unit", "window-sha256"):
        cli.add_argument("--" + field, required=True)
    a = cli.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    r = dict(status="FAIL_PRESERVED", generation_requests=0)

    def timed(*_):
        raise TimeoutError("fifteen-minute family")

    signal.signal(signal.SIGALRM, timed)
    signal.alarm(900)
    try:
        with (Path("/run/user") / str(os.getuid()) / "tesy-c110-callback.lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(a, out, r)
    except Exception as e:
        r["error"] = f"{type(e).__name__}: {e}"
    finally:
        signal.alarm(0)
    r["model_starts"] = len(list(out.glob("*/raw/*.launch.json")))
    r["raw_sha256"] = {
        str(f.relative_to(out)): sha(f) for f in sorted(out.rglob("*")) if f.is_file()
    }
    save(out / "receipt.json", r)
    print(r["status"], r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
