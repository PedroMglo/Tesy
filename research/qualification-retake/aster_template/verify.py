"""Compare the detached Harmony renderer in both linked backends with no model or tokenizer."""

import argparse
import hashlib
import json
import os
import re
import resource
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import two_turn_pair as historical  # noqa: E402

ORIGINAL = "a4c9919cbbd4acdd51ccffe22da049264b1b73e59055fa58811a99efbd7c8146"
C269 = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
STOCK = "e95426f16982054c379ca7bdc8186996dd22f0fe"
MIB = 1024**2


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rss(pid):
    p = Path("/proc") / str(pid)
    try:
        own = next(
            (
                int(s.split()[1])
                for s in (p / "status").read_text().splitlines()
                if s.startswith("VmRSS:")
            ),
            0,
        )
        children = (p / "task" / str(pid) / "children").read_text().split()
    except (OSError, ProcessLookupError):
        return 0
    return own + sum(rss(int(c)) for c in children)


def build(root, source, libs, tag, pin):
    rev = subprocess.check_output(["git", "-C", source, "rev-parse", "HEAD"], text=True).strip()
    check(rev == pin, "unverified source revision")
    path = root / tag
    cmd = [
        "/usr/bin/c++",
        "-std=c++17",
        "-O0",
        "-g0",
        "-pipe",
        "-ffile-prefix-map=" + str(HERE) + "=/tesy-aster",
    ]
    if tag == "C269":
        cmd.append("-DREFERENCE_C269")
    for inc in ["common", "include", "ggml/include", "vendor", "vendor/nlohmann", "tools/mtmd"]:
        cmd += ["-I", str(source / inc)]
    cmd += [
        str(HERE / "render.cpp"),
        "-L",
        str(libs),
        "-Wl,-rpath," + str(libs),
        "-lllama-common",
        "-lllama",
        "-lggml",
        "-lggml-base",
        "-o",
        str(path),
    ]

    def clamp():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (2 * MIB, 2 * MIB))

    with (
        (root / (tag + ".build.log")).open("xb") as log,
        subprocess.Popen(
            cmd,
            cwd=root,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            preexec_fn=clamp,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "TMPDIR": str(root)},
        ) as p,
    ):
        start = time.monotonic()
        peak = 0
        while p.poll() is None:
            peak = max(peak, rss(p.pid))
            if peak > 512 * 1024 or time.monotonic() - start > 60:
                os.killpg(p.pid, signal.SIGKILL)
                raise ValueError("compiler budget exceeded")
            time.sleep(0.03)
        check(p.returncode == 0, "compile failed for " + tag)
    return path, {
        "binary_sha256": sha(path.read_bytes()),
        "elapsed_s": round(time.monotonic() - start, 3),
        "tree_rss_peak_kib": peak,
    }


def render(exe, template, date, messages):
    chunks = []
    for row in messages:
        for k in ("role", "content"):
            b = row[k].encode()
            chunks.extend([struct.pack("<I", len(b)), b])
    p = subprocess.run(
        [exe, template, date],
        input=b"".join(chunks),
        capture_output=True,
        timeout=8,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "CUDA_VISIBLE_DEVICES": ""},
        check=False,
    )
    check(p.returncode == 0 and 0 < len(p.stdout) < 256 * 1024, "linked renderer rejected input")
    return p.stdout


def norm(data, day):
    old = b"Current date: " + day.encode() + b"\n"
    check(data.count(old) == 1, "dated system field absent or duplicated")
    return data.replace(old, b"Current date: [FROZEN]\n", 1)


def verify(a, root, r):
    manifest, _, users, history = historical.prepare(a.historical_results)
    r["input_sha256"] = historical.digest(manifest)
    tpl = Path("models/templates/openai-gpt-oss-120b.jinja")
    original = (a.stock_source / tpl).read_bytes()
    check(
        sha(original) == ORIGINAL and (a.c269_source / tpl).read_bytes() == original,
        "detached templates differ",
    )
    expr = b'strftime_now("%Y-%m-%d")'
    check(
        original.count(expr) == 1 and b"tesy_template_date" not in original, "ambiguous replacement"
    )
    adapted = original.replace(expr, b"tesy_template_date", 1)
    r["original_template_sha256"] = ORIGINAL
    r["adapted_template_sha256"] = sha(adapted)
    file = root / "fixed.jinja"
    with file.open("xb") as f:
        f.write(adapted)
    ref_lib = (a.c269_bin / "libllama-common.so").resolve(strict=True)
    stok_lib = (a.stock_bin / "libllama-common.so").resolve(strict=True)
    old = json.loads(
        next(
            (HERE.parents[2] / "results").glob("c281*/protocols/c281-r0-persistent.json")
        ).read_bytes()
    )
    stock_build = json.loads((HERE.parent / "stock_build/attempt-b/receipt.json").read_bytes())
    ref_dig = sha(ref_lib.read_bytes())
    stok_dig = sha(stok_lib.read_bytes())
    check(
        ref_dig in old["identity"]["library_sha256"].values()
        and stok_dig in stock_build["own_libs_sha256"].values(),
        "changed library",
    )
    r["linked_common_sha256"] = {"C269": ref_dig, "stock": stok_dig}
    ref, ref_build = build(root, a.c269_source, a.c269_bin, "C269", C269)
    stock, stock_stat = build(root, a.stock_source, a.stock_bin, "stock", STOCK)
    r["compilations"] = {"C269": ref_build, "stock": stock_stat}
    for exe, lib in [(ref, ref_lib), (stock, stok_lib)]:
        ld = subprocess.check_output(
            ["ldd", exe], text=True, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
        )
        selected = [
            Path(s.split("=>")[1].split()[0]).resolve(strict=True)
            for s in ld.splitlines()
            if "libllama-common.so" in s and "=>" in s
        ]
        check(selected == [lib] and "not found" not in ld, "wrong runtime selected")
    r["turns"] = []
    date = "2026-09-29"
    alternate = "2000-01-02"

    def pair(exe, tf, messages):
        return (render(exe, tf, date, messages), render(exe, tf, alternate, messages))

    for index, messages in enumerate([users[0], history]):
        baseline, negative = pair(ref, a.c269_source / tpl, messages)
        target, target_negative = pair(stock, a.stock_source / tpl, messages)
        fixed, fixed_negative = pair(stock, file, messages)
        row = {
            "turn": index + 1,
            "c269_sha256": sha(baseline),
            "stock_default_sha256": sha(target),
            "stock_bound_sha256": sha(fixed),
            "render_bytes": len(baseline),
            "stock_default_explicit_kwarg_digest_equal": target == target_negative,
            "stock_bound_matches_c269": fixed == baseline,
            "stock_bound_control_matches_c269": fixed_negative == negative,
        }
        r["turns"].append(row)
        actual = re.findall(rb"Current date: (\d{4}-\d\d-\d\d)\n", target)
        check(len(actual) == 1, "stock system date unavailable")
        check(
            baseline != negative
            and target == target_negative
            and target not in (baseline, negative),
            "date fixture does not distinguish inputs",
        )
        check(norm(baseline, date) == norm(negative, alternate), "C269 changed more than the date")
        check(
            norm(target, actual[0].decode()) == norm(baseline, date),
            "stock differs outside the system date",
        )
        check(
            fixed == baseline and fixed_negative == negative, "stock date-bound rendering diverged"
        )
    check(
        sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) < 8 * MIB,
        "private output budget exceeded",
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for name in [
        "stock-source",
        "stock-bin",
        "c269-source",
        "c269-bin",
        "historical-results",
        "private-workspace",
        "new-output-dir",
    ]:
        ap.add_argument("--" + name, required=True, type=Path)
    args = ap.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir()
    root = args.private_workspace.resolve()
    root.mkdir()
    record = {
        "status": "FAIL_PRESERVED",
        "forwards": 0,
        "model_files_opened": 0,
        "actual_gguf_template_match": "NOT_RUN",
        "official_tokenizer_ids": "NOT_RUN",
        "cache_observation": "NOT_RUN",
        "product_response": "NOT_RUN",
        "protocol_sha256": sha((HERE / "protocol.md").read_bytes()),
        "sources": {p.name: sha(p.read_bytes()) for p in [Path(__file__), HERE / "render.cpp"]},
    }
    try:
        verify(args, root, record)
        record["status"] = "PASS_DETACHED_RENDER_ONLY"
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as exc:
        record["error"] = str(exc)
    with (args.new_output_dir / "receipt.json").open("x") as f:
        json.dump(record, f, sort_keys=True, indent=2)
        f.write("\n")
    print(record["status"], record.get("error", ""))
    raise SystemExit(int(record["status"] != "PASS_DETACHED_RENDER_ONLY"))
