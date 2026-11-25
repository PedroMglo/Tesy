"""Build the C269 proposal/acceptance fixture or compare its steps on sealed IDs."""

import argparse
import hashlib
import importlib.util
import json
import os
import shlex
import struct
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
REPO = HERE.parents[4]
C269 = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
VERIFIED = "494101d84e2696670bf59589768c3a7208db1c6b0b5ac1f6f914d3d9f264f08d"
SCREEN = "649bc3fe8f9e6469ab5cf7519ded4c5cb7d684cf36c792ca2a4b5eba018a7cbf"
CERT = PARENT.parent / "natural47/evidence/build-r02.json"
RULE = PARENT.parent / "causal_pair/screen.py"
RULE_SHA = "797746256c463790abc44463e56948636fa63b03f9d0e710daa29203f8a9846e"
PROTOCOL = "d95c1dd9c9be7f4a79e516c127686a7a1f0b9aa259abad500dd6f0cc282fe3a1"
CAPTURE = "8825a62338b9aebf913b3dc676dfb5b17ffa98885604e5f12091a3d47cae5f3a"
CERT_SHA = "e9662585b863443bb74d088701f5fc580d03ae7be344cc9f899df523246afe58"
LIB = "libllama-common.so.0.0.9884"
COMMON = "cc5a0f0b264bdd093287cfdb38f3607b8ab98bd35ae21f4550ddc44076c92d27"


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    with path.open("rb") as s:
        return hashlib.file_digest(s, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def pinned(path, expect):
    check(sha(path) == expect, "digest: " + path.name)
    return read(path)


def git(repo, *args):
    return subprocess.check_output(["git", "-C", repo, *args]).strip().decode()


def authority(backend):
    check(git(backend, "rev-parse", "HEAD") == C269, "backend pin")
    cert = pinned(CERT, CERT_SHA)
    check(
        cert["library_sha256"][LIB] == COMMON
        and sha(Path("/usr/bin/g++")) == cert["compiler_sha256"],
        "build authority",
    )
    libs = backend / "build-c269-cuda/bin"
    env = dict(
        PATH="/usr/bin:/bin",
        LC_ALL="C",
        LD_LIBRARY_PATH=str(libs),
        CUDA_VISIBLE_DEVICES="",
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
    )
    return libs, env, cert


def providers(exe, env, cert):
    text = subprocess.check_output(["/usr/bin/ldd", exe], env=env, text=True)
    check("not found" not in text, "unresolved native library")
    linked = {
        Path(line.split()[2]).resolve(strict=True) for line in text.splitlines() if " => /" in line
    }
    actual = {
        p.name: sha(p) for p in linked if p.name.startswith(("libllama", "libggml", "libmtmd"))
    }
    check(
        len(actual) >= 2
        and actual.get(LIB) == COMMON
        and all(cert["resolved_elf_sha256"].get(k) == v for k, v in actual.items()),
        "linked C269 providers",
    )
    return actual


def build(a, out):
    libs, env, cert = authority(a.backend)
    exe = out / "fixture"
    dep = out / "headers.d"
    source = HERE / "native.cpp"
    cmd = [
        "/usr/bin/g++",
        "-std=c++17",
        "-O0",
        "-g0",
        "--param",
        "ggc-min-expand=8",
        "--param",
        "ggc-min-heapsize=8192",
        "-fPIC",
        "-pie",
        "-fno-plt",
        "-Wl,--export-dynamic",
        "-MMD",
        "-MF",
        dep,
    ]
    for directory in ("common", "include", "ggml/include", "vendor", "vendor/nlohmann"):
        cmd += ["-I", a.backend / directory]
    cmd += [source, libs / "libllama-common.so", "-ldl", f"-Wl,-rpath-link,{libs}", "-o", exe]
    with (out / "compile.log").open("xb") as log:
        rc = subprocess.run(
            cmd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=110, check=False
        ).returncode
    check(rc == 0, "C269 fixture build, see private compile.log")
    dependencies = shlex.split(dep.read_text().replace("\\\n", " ").split(":", 1)[1])
    headers = {}
    for raw in dependencies:
        path = Path(raw).resolve(strict=True)
        if path == source:
            continue
        name = path.relative_to(a.backend.resolve(strict=True)).as_posix()
        blob = subprocess.check_output(["git", "-C", a.backend, "show", C269 + ":" + name])
        check(digest(blob) == sha(path), "header " + name)
        headers[name] = digest(blob)
    check(
        "common/ngram-map.h" in headers and "common/sampling.h" in headers,
        "C269 sampling/proposer headers",
    )
    return dict(
        status="PASS_C269_B3_FIXTURE_BUILD",
        binary_sha256=sha(exe),
        compiler_sha256=cert["compiler_sha256"],
        source_sha256=sha(source),
        headers_sha256=headers,
        providers=providers(exe, env, cert),
    )


def python_rule():
    check(sha(RULE) == RULE_SHA, "frozen Python proposal rule")
    spec = importlib.util.spec_from_file_location("reference_ngram", RULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def trace(rule, prompt, target, end):
    check(1 <= end < len(target), "window")
    observed = tuple(target[1 : end + 1])
    pos = 0
    history = tuple(prompt) + tuple(target[:1])
    rows = []
    while pos < end:
        draft = rule.draft(history, 2, 2)
        accepted = 0
        mismatch = False
        for token in draft:
            if pos + accepted == end:
                break
            if token != observed[pos + accepted]:
                mismatch = True
                break
            accepted += 1
        advance = accepted + int(pos + accepted < end)
        boundary = bool(draft) and not mismatch and pos + accepted == end
        rows.append(
            dict(
                position=pos,
                proposed=len(draft),
                accepted_draft=accepted,
                emitted=advance,
                discarded_draft=len(draft) - accepted,
                verifier_rows=advance if draft else 0,
                beyond_window_rows=0,
                ar=not draft,
                mismatch=mismatch,
                boundary_interrupted=boundary,
                unavailable_row_attempts=int(boundary),
                unobserved_draft=(len(draft) - accepted if boundary else 0),
            )
        )
        history += observed[pos : pos + advance]
        pos += advance
    check(history == tuple(prompt) + tuple(target[: end + 1]), "reference prefix consistency")
    return rows


def compare_case(exe, env, libs, rule, out, label, prompt, target, end):
    expected = trace(rule, prompt, target, end)
    summary = rule.replay(prompt, target[: end + 1], 2, 2)
    payload = json.dumps(dict(prompt=prompt, target=target, end=end)).encode()
    run = subprocess.run(
        [exe],
        input=payload,
        capture_output=True,
        env=env,
        timeout=30,
        check=False,
    )
    for stream, data in (("stdout", run.stdout), ("stderr", run.stderr)):
        with (out / (label + "." + stream)).open("xb") as f:
            f.write(data)
    check(run.returncode == 0, "native exit for " + label + " (" + str(run.returncode) + ")")
    raw = json.loads(run.stdout)
    check(
        raw["status"] == "PASS_C269_B3_NATIVE_CONTROL"
        and raw["window"] == end
        and raw["callbacks_in_executable"] is True
        and raw["history_equal"] is True,
        "native control gates for " + label,
    )
    for provider in ("lookup_provider", "verify_provider"):
        check(
            Path(raw[provider]).resolve(strict=True) == (libs / LIB).resolve(strict=True),
            "native function provider",
        )
    got = raw["events"]
    check(len(got) == len(expected), "step count " + label)
    for i, (r, e) in enumerate(zip(got, expected, strict=True)):
        for k, v in e.items():
            check(type(r.get(k)) is type(v) and v == r[k], f"{label} step {i} {k}")
    for key, value in summary.items():
        check(
            type(raw["summary"].get(key)) is int and raw["summary"][key] == value,
            label + " summary " + key,
        )
    check(
        raw["stop_placeholders"] == 0
        and raw["logical_rollback_rows"] == sum(e["discarded_draft"] for e in expected)
        and raw["boundary_interruptions"] == sum(e["unavailable_row_attempts"] for e in expected),
        label + " control totals",
    )
    classes = {
        str(k): sum(1 for e in expected if e["proposed"] == 2 and e["accepted_draft"] == k)
        for k in range(3)
    }
    # Only the explicitly enumerated fields above can leave the private process.
    return dict(
        label=label,
        end=end,
        summary=summary,
        accepted_draft_by_call=classes,
        logical_discarded_rows=sum(e["discarded_draft"] for e in expected),
        boundary_interruptions=sum(e["boundary_interrupted"] for e in expected),
        mismatches=sum(e["mismatch"] for e in expected),
        events=expected,
    )


def replay(a, out):
    libs, env, cert = authority(a.backend)
    report = pinned(a.build_dir / "receipt.json", a.build_sha256)
    exe = a.build_dir / "fixture"
    check(
        report["status"] == "PASS_C269_B3_FIXTURE_BUILD"
        and sha(exe) == report["binary_sha256"]
        and sha(HERE / "native.cpp") == report["source_sha256"]
        and report["providers"] == providers(exe, env, cert),
        "fixture build authority",
    )
    rule = python_rule()
    prompt = [90, 1, 2, 3, 4, 80, 1]
    baseline_cases = [
        ("no_match", [91, 92, 93, 94, 95, 96, 97], [7, 8, 9], 2),
        ("zero", prompt, [2, 8, 7, 9], 3),
        ("one", prompt, [2, 3, 8, 9], 3),
        ("both_bonus", prompt, [2, 3, 4, 8], 3),
        ("cut_after_one", prompt, [2, 3, 4, 8], 1),
        ("cut_before_bonus", prompt, [2, 3, 4, 8], 2),
    ]
    synthetic = [compare_case(exe, env, libs, rule, out, *c) for c in baseline_cases]
    check(
        [s["events"][0]["accepted_draft"] for s in synthetic[1:4]] == [0, 1, 2]
        and synthetic[0]["events"][0]["ar"]
        and synthetic[4]["boundary_interruptions"] == 1
        and synthetic[5]["boundary_interruptions"] == 1,
        "synthetic failure coverage",
    )
    ver = pinned(a.verified / "receipt.json", VERIFIED)
    screen = pinned(PARENT / "evidence/b3.json", SCREEN)
    pinned(a.capture / "receipt.json", CAPTURE)
    check(
        ver["capture_receipt_sha256"] == CAPTURE and screen["verified_sha256"] == VERIFIED,
        "trajectory provenance",
    )
    inp = pinned(
        a.capture / "raw/T2-input.json", ver["capture_turn_files_sha256"]["T2-input.json"]
    )["official_ids"]
    dat = (a.verified / "T2-sampled.i32").read_bytes()
    check(
        len(dat) == 47 * 4
        and digest(dat) == ver["turns"][1]["sampled_ids_sha256"]
        and len(inp) == 2197
        and digest(struct.pack("<2197i", *inp)) == screen["prompt_i32_sha256"]
        and ver["turns"][1]["unique_final_eog"] is True,
        "private official input/target",
    )
    ids = struct.unpack("<47i", dat)
    real = [
        compare_case(exe, env, libs, rule, out, "natural" + str(end), inp, ids, end)
        for end in (32, 46)
    ]
    for row, old in zip(real, screen["windows"], strict=True):
        check(all(old[k] == v for k, v in row["summary"].items()), "prior screen mismatch")
    return dict(
        status="PASS_C269_B3_NATIVE_CONTROL_ONLY",
        model_forwards=0,
        real_kv_rollback="NOT_RUN",
        physical_cold_bytes="NOT_MEASURED",
        build_sha256=a.build_sha256,
        verified_sha256=VERIFIED,
        screen_sha256=SCREEN,
        compiler_sha256=cert["compiler_sha256"],
        providers=report["providers"],
        synthetic=synthetic,
        natural=real,
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="action", required=True)
    for action in ("build", "replay"):
        q = sub.add_parser(action)
        for flag in ("backend", "new-output-dir"):
            q.add_argument("--" + flag, required=True, type=Path)
        if action == "replay":
            for flag in ("build-dir", "capture", "verified"):
                q.add_argument("--" + flag, required=True, type=Path)
            q.add_argument("--build-sha256", required=True)
    a = ap.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    started = time.monotonic()
    try:
        check(
            git(REPO, "status", "--porcelain") == "" and sha(HERE / "protocol.md") == PROTOCOL,
            "clean checkout/protocol",
        )
        r = (build if a.action == "build" else replay)(a, out)
    except Exception as exc:
        r = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    r.update(
        elapsed_s=time.monotonic() - started,
        program_sha256=sha(Path(__file__)),
        commit=git(REPO, "rev-parse", "HEAD"),
        protocol_sha256=PROTOCOL,
    )
    sized = sum(p.stat().st_size for p in out.iterdir() if p.is_file())
    if r["elapsed_s"] > 120 or sized + len(json.dumps(r, indent=2).encode()) + 1 > 8 * 2**20:
        r.update(status="FAIL_PRESERVED", reason="time or output budget")
    with (out / "receipt.json").open("x") as stream:
        json.dump(r, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    print(r["status"])
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
