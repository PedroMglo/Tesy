"""Compare fresh C269 AR and B3 numerical arms on the fixed C127 prefix under E20."""

import argparse
import copy
import hashlib
import importlib.util
import os
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
Q = HERE.parents[1]
R0 = Q / "nvme_r0_gate"
src = importlib.util.spec_from_file_location("c270_qualified", R0 / "qualified_profile/profile.py")
base = importlib.util.module_from_spec(src)
src.loader.exec_module(base)
sys.path.insert(0, str(HERE))
import logits_grade  # noqa: E402

need, read, save, sha = base.need, base.read, base.save, base.sha
C270 = "1f332ad437d90c24adf3b88b87ddf0dac8e13b7e87e818d93461ffd281c801b6"
WORKER = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
SOURCE = "295e710af6efbd59944ae999911aeb94f0a7aef633895f1f3404161e56bdb0e6"
PROTOCOL = "a29319ae8f4700d42a74cfd3c372eda79245f52a911d57b644b438f096956b68"
IDS = "8fb3aff447febaeaa5a8bdd0c485fd20d51d39fb6ac3e6ba4849eb4a664dbc23"
ROWS = ("prefill_final", "decode0", "decode1", "decode2", "decode3")
MIB = 2**20


def select_bin(directory, digest, preflight_sha):
    p = directory / "receipt.json"
    need(sha(p) == digest, "build receipt")
    b = read(p)
    need(
        b["status"] == "PASS_C269_B3_NUMERIC_BUILD"
        and b["static_preflight_sha256"] == preflight_sha
        and b["executable"] == "b3-numeric"
        and b["worker_commit"] == WORKER
        and b["parent_capture_source_sha256"] == SOURCE
        and b["native_source_sha256"] == sha(HERE / "native.cpp"),
        "derived client origin",
    )
    exe = (directory / b["executable"]).resolve(strict=True)
    need(sha(exe) == b["binary_sha256"], "derived executable digest")
    return exe, b["binary_sha256"]


class DerivedAuthority(base.Authority):
    """Keep every C270 DSO, alias, FD/VMA and loader check; authenticate only the new main ELF."""

    def __init__(self, a, exe, exe_sha):
        super().__init__(a.checkout, a.preflight_dir, a.preflight_sha256, "C270")
        text = self.static.command(
            [self.static.LOADER, "--list", exe], self.static.environment(self.arm["native_search"])
        )
        links = {
            name: [str(path), str(path.resolve(strict=True))]
            for name, path in self.static.interpret(text).items()
        }
        need(links == self.links, "derived startup object identities differ from C270")
        self.exe = exe
        self.arm = dict(self.arm, executable=str(exe), executable_sha256=exe_sha)
        self.new_stat = stat(exe)

    def recheck(self):
        super().recheck()
        if hasattr(self, "new_stat"):
            need(stat(self.exe) == self.new_stat, "derived executable changed")


def stat(path):
    st = path.stat()
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def derivative_command(command, old_exe, new_exe, gold, mode, unit, protocol):
    cmd = list(command)
    start = len(cmd) - 6
    need(
        mode in ("AR", "B3")
        and cmd[start - 1] == "--"
        and Path(cmd[start]).resolve(strict=True) == old_exe
        and cmd[-2:] == ["--ngl", "12"]
        and Path(cmd[start + 3]).name == unit + ".capture",
        "base C270 CLI",
    )
    need(cmd.count("LimitFSIZE=8388608") == 1, "historical per-file guard")
    cmd[cmd.index("LimitFSIZE=8388608")] = "LimitFSIZE=" + str(40 * MIB)
    cmd[cmd.index("--variant") + 1] = "C269-B3-numeric189-" + mode
    cmd[cmd.index("--resource-protocol") + 1] = str(protocol)
    return cmd[:start] + [
        str(new_exe),
        cmd[start + 1],
        cmd[start + 2],
        str(gold),
        mode,
        cmd[start + 3],
    ]


def raw_capture(control):
    rec = control / "receipt.json"
    need(sha(rec) == C270, "contemporary C270 closure")
    r = read(rec)
    need(
        r["status"] == "PASS_SELECTED_C269_BRIDGE"
        and r["envelope"] == "E20_R0"
        and sha(control / "protocol.json") == r["protocol_sha256"],
        "C270 bridge",
    )
    protocol = read(control / "protocol.json")
    rid = protocol["execution_scope_unit"]
    need(
        Path(rid).name == rid
        and sha(control / "selected.json") == r["selected_sha256"]
        and sha(control / "raw" / (rid + ".json")) == r["monitor_sha256"],
        "C270 closure links",
    )
    base_dir = control / "raw" / (rid + ".capture")
    for name, digest in protocol["pinned"]["gold_full_logits_sha256"].items():
        need(sha(base_dir / (name + ".logits.f32")) == digest, "historical raw logits " + name)
    return base_dir, protocol["pinned"]


def row(directory, name):
    return directory / (name + ".logits.f32")


def check_prefix(directory, gold):
    files = sorted(x.name for x in directory.glob("prefill*"))
    reference = sorted(x.name for x in gold.glob("prefill*"))
    need(len(files) == 2248 and files == reference, "complete prefill witness inventory")
    total = 0
    h = hashlib.sha256()
    for name in files:
        path = directory / name
        size = path.stat().st_size
        matches = sha(path)
        need(
            size == (gold / name).stat().st_size and matches == sha(gold / name),
            "prefill payload " + name,
        )
        total += size
        h.update(name.encode() + b"\0" + str(size).encode() + b"\0" + bytes.fromhex(matches))
    need(total == 81624144, "prefill size")
    return dict(files=len(files), bytes=total, ordered_name_size_digest_sha256=h.hexdigest())


def require_arm(directory, mode, gold, official):
    native = read(directory / "native.json")
    need(
        native["status"] == "PASS_B3_NUMERIC_ARM"
        and native["mode"] == mode
        and native["prefix_rows"] == 189
        and native["prefill_files"] == 2248
        and native["prefill_bytes"] == 81624144
        and native["verification_rows"] == 3
        and native["continuation_rows"] == 1
        and native["vocab"] == 201088
        and native["positions"] == list(range(189, 193))
        and native["historical_ar_rows_checked"] == (2 if mode == "AR" else 0)
        and native["initial_state_checked_before_block"] is (mode == "B3"),
        "native completeness",
    )
    prefix = check_prefix(directory, gold)
    for name in ROWS:
        need(row(directory, name).stat().st_size == 804352, "row size " + name)
    comparisons = {}
    for name in ROWS[:3] if mode == "AR" else ROWS[:1]:
        baseline = logits_grade.compare_rows(row(gold, name), row(directory, name))
        need(
            baseline["bitwise"] and baseline["reference_sha256"] == official[name],
            "historical row " + name,
        )
        comparisons[name] = baseline
    states = {}
    for filename in ("initial-kv.bin", "initial-pool.bin", "post3-kv.bin"):
        path = directory / filename
        size = path.stat().st_size
        need(path.is_file() and not path.is_symlink() and 0 < size <= 32 * MIB, "state " + filename)
        states[filename] = {"bytes": size, "sha256": sha(path)}
    # Check finiteness of the new AR references even before admitting the next model.
    if mode == "AR":
        for name in ROWS[3:]:
            need(
                logits_grade.compare_rows(row(directory, name), row(directory, name))["finite"],
                "AR finiteness",
            )
    return dict(
        native_sha256=sha(directory / "native.json"),
        prefix=prefix,
        historical=comparisons,
        states=states,
    )


def compare_pair(ref, actual, r, b):
    need(
        r["prefix"] == b["prefix"]
        and all(r["states"][n] == b["states"][n] for n in ("initial-kv.bin", "initial-pool.bin")),
        "initial states or observations differ",
    )
    grades = {
        name: logits_grade.compare_rows(row(ref, name), row(actual, name)) for name in ROWS[1:]
    }
    same_bits = all(g["bitwise"] for g in grades.values())
    same_greedy = all(g["same_greedy"] for g in grades.values())
    post3 = r["states"]["post3-kv.bin"] == b["states"]["post3-kv.bin"]
    return dict(
        status="PASS_BITS_AND_OBSERVED_STATE"
        if same_bits and post3
        else "DIFFERENT_LOGIT_BITS_OR_CARRY_STATE",
        rows=grades,
        all_four_bitwise=same_bits,
        all_four_unique_greedy_equal=same_greedy,
        initial_kv_equal=True,
        initial_pool_equal=True,
        post3_kv_equal=post3,
        first_unequal_logit_row=next((n for n, g in grades.items() if not g["bitwise"]), None),
        cross_shape_tolerance="NOT_DEFINED",
        rollback="NOT_RUN",
        nominal_history="NOT_RUN",
    )


def teacher_prefix(ids):
    need(sha(ids) == IDS, "teacher input authority")
    lines = [
        line.split("\t")
        for line in ids.read_text().splitlines()
        if line.split("\t", 1)[0] == "log_medium"
    ]
    need(len(lines) == 1 and len(lines[0]) == 3, "teacher case identity")
    prompt = [int(v) for v in lines[0][1].split(",")]
    next_ids = [int(v) for v in lines[0][2].split(",")]
    need(
        len(prompt) == 189
        and len(next_ids) == 43
        and all(0 <= v < 201088 for v in prompt + next_ids),
        "teacher geometry",
    )
    return next_ids[:4]


def next_ids_match(directory, teacher):
    result = []
    for name, supplied in zip(ROWS[:4], teacher, strict=True):
        vals = struct.unpack("<201088f", row(directory, name).read_bytes())
        top = max(vals)
        result.append(
            dict(after=name, supplied_is_max=vals[supplied] == top, unique_max=vals.count(top) == 1)
        )
    return result


def run_arm(args, folder, unit, mode, exe, exe_sha, control, old_pins, paired=None):
    folder.mkdir(mode=0o700)
    a = copy.copy(args)
    a.unit = unit
    a.execute = False
    template = base.prepare_campaign(a, folder)
    need(template["status"] == "PREPARED_ONLY", "base admission")
    # The base protocol and command remain independently reproducible control records.
    original = read(folder / "qualified-protocol.json")
    protocol = read(folder / "protocol.json")
    sealed = protocol["pinned"]
    need(
        sealed == old_pins and sealed["backend_commit"] == WORKER and sealed["ids_sha256"] == IDS,
        "frozen inputs changed",
    )
    authority = DerivedAuthority(a, exe, exe_sha)
    original_cmd = original["monitor"]
    start = len(original_cmd) - 6
    old_exe = Path(original_cmd[start]).resolve(strict=True)
    need(sha(old_exe) == sealed["capture_sha256"], "original executable mismatch")
    ids = Path(original_cmd[start + 2])
    teacher = teacher_prefix(ids)
    gold = Path(original["check"][-1]).resolve(strict=True)
    new_sealed = sealed | {"capture_sha256": exe_sha}
    deriv = protocol | {
        "schema": "tesy-c269-b3-numeric-189-v1",
        "pinned": new_sealed,
        "contrast": mode,
        "base_c270_receipt_sha256": C270,
        "scientific_protocol_sha256": PROTOCOL,
    }
    new_protocol = folder / "b3-resource-protocol.json"
    save(new_protocol, deriv)
    # Only the B3 child uses this arm's live AR control as its immediate numerical gate.
    # All historical output checks below still use the independent C127 and C270.
    child_gold = gold
    if mode == "B3":
        need(paired is not None, "missing preceding AR arm")
        child_gold, ar_receipt = paired
        if args.execute:
            need(ar_receipt["status"] == "PASS_NUMERIC_ARM_AR", "AR gate failed")
            for name in ("initial-kv.bin", "initial-pool.bin"):
                expected = ar_receipt["grade"]["states"][name]
                witness = child_gold / name
                need(
                    witness.stat().st_size == expected["bytes"]
                    and sha(witness) == expected["sha256"],
                    "preceding AR state identity",
                )
    cmd = derivative_command(original_cmd, old_exe, exe, child_gold, mode, unit, new_protocol)
    save(
        folder / "b3-command.json",
        dict(command=cmd, original_preset_sha256=sha(folder / "qualified-protocol.json")),
    )
    partial = dict(
        status="PREPARED_ONLY",
        model_launch_receipts=0,
        unit=unit,
        mode=mode,
        derived_protocol_sha256=sha(new_protocol),
        execution_argv_sha256=sha(folder / "b3-command.json"),
    )
    save(folder / "prepared.json", partial)
    if not args.execute:
        return partial, None
    import measure
    import run_bounded

    raw = folder / "raw"
    partial["monitor_provider"] = authority.monitor_proof()
    need(
        run_bounded.file_identity(Path(cmd[-5])) == protocol["model_stat"], "changed model identity"
    )
    ident, n, seen, wall = base.guarded_run(cmd, folder, unit, authority, measure, run_bounded)
    mp = raw / (unit + ".json")
    lp = raw / (unit + ".launch.json")
    m = read(mp)
    need(
        m["process_identity"] == ident == read(lp)["process_identity"] and m["command"] == cmd[-6:],
        "actual arm invocation",
    )
    base.check_native_manifest(m, deriv, new_sealed, original["native_explicit_env"], measure)
    audit = authority.audit(raw / "loader", ident["pid"])
    need(
        set(audit["initialized_sha256"]) >= {Path(p).name for p in seen}
        and measure.file_bytes(raw) <= 128 * MIB
        and wall <= 320,
        "runtime audit or budget",
    )
    save(folder / "loader-audit.json", audit)
    cap_path = raw / (unit + ".capture")
    validated = require_arm(cap_path, mode, gold, old_pins["gold_full_logits_sha256"])
    # C127 gold and authenticated contemporary C270 give identical independent reference rows.
    for name, g in validated["historical"].items():
        need(g["reference_sha256"] == sha(row(control, name)), "C270 contemporary control row")
    result = partial | dict(
        status="PASS_NUMERIC_ARM_" + mode,
        model_launch_receipts=1,
        grade=validated,
        unique_teacher_match=next_ids_match(cap_path, teacher),
        maxima=m["maxima"],
        native_elapsed_s=m["elapsed_s"],
        scope_wall_s=wall,
        raw_bytes=measure.file_bytes(raw),
        live_samples=n,
        loader_audit_sha256=sha(folder / "loader-audit.json"),
        c118_sha256=sha(raw / (unit + ".start-inventory.jsonl")),
        monitor_sha256=sha(mp),
        launch_sha256=sha(lp),
        provider_sha256=audit["initialized_sha256"],
    )
    return result, cap_path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in (
        "checkout",
        "preflight-dir",
        "window",
        "placement",
        "c270-dir",
        "build-dir",
        "new-output-dir",
    ):
        ap.add_argument("--" + name, required=True, type=Path)
    for name in ("preflight-sha256", "window-sha256", "measurement-commit", "unit", "build-sha256"):
        ap.add_argument("--" + name, required=True)
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    started = time.monotonic()
    arms = {}
    try:
        need(sha(HERE / "protocol.md") == PROTOCOL, "scientific registration")
        exe, exe_sha = select_bin(a.build_dir, a.build_sha256, a.preflight_sha256)
        control, old_pins = raw_capture(a.c270_dir)
        require_src = (
            a.checkout / "research/qualification-retake/history_lookup/b3_numeric/profile.py"
        )
        need(require_src.resolve() == Path(__file__).resolve(), "foreign supervisor")
        paths = {}
        for mode in ("AR", "B3"):
            folder = out / mode
            unit = a.unit + "-" + mode.lower()
            try:
                paired = None
                if mode == "B3":
                    ar_path = out / "AR" / "raw" / (a.unit + "-ar.capture")
                    paired = (ar_path, arms["AR"])
                arm, path = run_arm(a, folder, unit, mode, exe, exe_sha, control, old_pins, paired)
            except Exception as exc:
                raw = folder / "raw"
                folder.mkdir(exist_ok=True)
                arm = dict(
                    status="FAIL_PRESERVED",
                    mode=mode,
                    reason=f"{type(exc).__name__}: {exc}",
                    model_launch_receipts=len(list(raw.glob("*.launch.json"))),
                    observed_raw_bytes=sum(p.stat().st_size for p in raw.rglob("*") if p.is_file()),
                )
                arms[mode] = arm
                save(folder / "receipt.json", arm)
                raise
            arms[mode] = arm
            paths[mode] = path
            save(folder / "receipt.json", arm)
            need(time.monotonic() - started <= 720, "family wall")
        pair = (
            compare_pair(paths["AR"], paths["B3"], arms["AR"]["grade"], arms["B3"]["grade"])
            if a.execute
            else {}
        )
        result = dict(status=pair.get("status", "PREPARED_ONLY"), outcome=pair)
    except Exception as exc:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    result.update(
        arms={
            k: {
                "status": v["status"],
                "model_launch_receipts": v["model_launch_receipts"],
                "receipt_sha256": sha(out / k / "receipt.json"),
            }
            for k, v in arms.items()
        },
        envelope_s=time.monotonic() - started,
        measurement_commit=a.measurement_commit,
        build_sha256=a.build_sha256,
        c55_sha256=a.window_sha256,
        protocol_sha256=PROTOCOL,
        program_sha256=sha(Path(__file__)),
        historical_c270_sha256=C270,
    )
    if result["envelope_s"] > 720:
        result.update(status="FAIL_PRESERVED", reason="family wall")
    save(out / "receipt.json", result)
    print(result["status"], flush=True)
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
