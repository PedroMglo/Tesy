"""Verify both C133 prompt vectors using only the header of the identified NVMe GGUF."""

import argparse
import json
import os
import resource
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "aster_template"))
from verify import C269, MIB, ORIGINAL, STOCK, check, historical, render, rss, sha  # noqa: E402

BOUND = 13_022_240
PRIOR = "b906de70d9d2f4f2eebc3187844d03064f16a3c15d3ca6721448cfbec47a90d4"
PLACEMENT = "50a35a1e5c3fde78066d1378e13dfeb89867d9970528135ff3294c6aa5bd1bf7"
WINDOW = "80389676b0e4112e5de0b5f00866f0590165082a973c5b671f085580f92f71dd"
C7 = "014a2ebc08e6aa3ecdbd3b0d5753e2664ac0d2d1b4c615ebefe46131eae826f2"


def verified(path, expected):
    data = path.read_bytes()
    check(sha(data) == expected, "receipt changed")
    return json.loads(data)


def bounded(argv, root, label, record, payload=b""):
    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE, (16 * MIB, 16 * MIB))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    with (
        (root / (label + ".log")).open("xb") as log,
        subprocess.Popen(
            argv,
            cwd=root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log,
            env={
                "PATH": "/usr/bin:/bin",
                "LC_ALL": "C",
                "CUDA_VISIBLE_DEVICES": "",
                "TMPDIR": str(root),
            },
            start_new_session=True,
            preexec_fn=limits,
        ) as proc,
    ):
        start = time.monotonic()
        peak = 0
        while True:
            peak = max(peak, rss(proc.pid))
            if peak > 512 * 1024 or time.monotonic() - start > 60:
                os.killpg(proc.pid, signal.SIGKILL)
                raise ValueError("child budget exceeded: " + label)
            try:
                out, _ = proc.communicate(payload, timeout=0.025)
                break
            except subprocess.TimeoutExpired:
                payload = None
        record["children"][label] = {
            "wall_s": round(time.monotonic() - start, 3),
            "rss_tree_peak_kib": peak,
            "returncode": proc.returncode,
        }
        check(proc.returncode == 0 and len(out) <= 128 * 1024, "private child failed: " + label)
        return out


def fields(data):
    parts = []
    while data:
        check(len(data) >= 4, "truncated result")
        n = struct.unpack_from("<I", data)[0]
        check(0 < n <= len(data) - 4, "invalid field length")
        parts.append(data[4 : 4 + n])
        data = data[4 + n :]
    return parts


def compile_probe(name, source, libs, hashes, root, rec):
    rev = subprocess.check_output(["git", "-C", source, "rev-parse", "HEAD"], text=True).strip()
    check(rev == (C269 if name == "C269" else STOCK), "source pin changed")
    cpp = HERE / "probe.cpp"
    exe = root / name
    cmd = ["/usr/bin/c++", "-std=c++17", "-pipe", "-O0", "-g0"]
    if name == "C269":
        cmd.append("-DREFERENCE_C269")
    cmd.extend(
        [
            "-I",
            source / "include",
            "-I",
            source / "ggml/include",
            cpp,
            "-L",
            libs,
            "-Wl,-rpath," + str(libs),
            "-lllama",
            "-lggml-base",
            "-o",
            exe,
        ]
    )
    bounded(cmd, root, name + "-compile", rec)
    loaded = subprocess.check_output(
        ["ldd", exe], text=True, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
    )
    selected = {}
    for soname in ("libllama.so", "libggml-base.so"):
        keys = [
            line.split("=>")[1].split()[0]
            for line in loaded.splitlines()
            if line.strip().startswith(soname) and "=>" in line
        ]
        check(len(keys) == 1 and "not found" not in loaded, "loader")
        p = Path(keys[0]).resolve(strict=True)
        check(p == (libs / soname).resolve(strict=True), "wrong dynamic library")
        h = sha(p.read_bytes())
        check(h in hashes, "DSO differs from historical identity")
        selected[soname] = h
    rec["libraries_sha256"][name] = selected
    rec["executables_sha256"][name] = sha(exe.read_bytes())
    return exe


def run(a, r):
    prior = verified(HERE.parent / "aster_template/attempt-01/receipt.json", PRIOR)
    manifest, _, users, history = historical.prepare(a.historical_results)
    check(historical.digest(manifest) == prior["input_sha256"], "C133 manifest differs")
    private = a.private_workspace.resolve()
    private.mkdir()
    rendered = {}
    original = Path("models/templates/openai-gpt-oss-120b.jinja")
    for name, template in [
        ("C269", a.c269_source / original),
        ("stock", a.stock_source / original),
        ("bound", a.render_workspace / "fixed.jinja"),
    ]:
        arm = "stock" if name == "bound" else name
        path = a.render_workspace / arm
        check(
            sha(path.read_bytes()) == prior["compilations"][arm]["binary_sha256"],
            "renderer changed",
        )
        check(
            sha(template.read_bytes())
            == (prior["adapted_template_sha256"] if name == "bound" else ORIGINAL),
            "template changed",
        )
        rendered[name] = [
            render(path, template, historical.POLICY["date"], msg) for msg in (users[0], history)
        ]
    check(
        all(
            sha(s) == row["c269_sha256"]
            for s, row in zip(rendered["C269"], prior["turns"], strict=True)
        ),
        "historical rendered bytes",
    )
    check(rendered["bound"] == rendered["C269"], "adapted template mismatch")
    ref0 = json.loads(
        next((ROOT / "results").glob("c281*/protocols/c281-r0-persistent.json")).read_bytes()
    )
    stock0 = json.loads((HERE.parent / "stock_build/attempt-b/receipt.json").read_bytes())
    ref = compile_probe(
        "C269", a.c269_source, a.c269_bin, ref0["identity"]["library_sha256"].values(), private, r
    )
    stock = compile_probe(
        "stock", a.stock_source, a.stock_bin, stock0["own_libs_sha256"].values(), private, r
    )
    plan = verified(a.placement, PLACEMENT)
    window = verified(a.window, WINDOW)
    account = verified(ROOT / "results/c7-20260927T1130Z/accounting.json", C7)
    check(
        account["model_data_offset"] == BOUND
        and account["tensor_count"] == 687
        and plan["destination_direct_reread"]["sha256"] == historical.MODEL,
        "historical placement or tensor boundary",
    )

    def ident(st):
        return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]

    with Path(plan["working_copy"]).open("rb", buffering=0) as gguf:
        check(ident(os.fstat(gguf.fileno())) == window["selected_stat"], "model stat changed")
        header = os.pread(gguf.fileno(), BOUND, 0)
        check(
            len(header) == BOUND and ident(os.fstat(gguf.fileno())) == window["selected_stat"],
            "incomplete header or mutated input",
        )
    r.update(
        model_sha256_prior_verified=historical.MODEL,
        header_sha256=sha(header),
        original_bytes_requested=BOUND,
    )
    headerpath = private / "header"
    headerpath.write_bytes(header)
    vocab = private / "vocab.gguf"
    r["kv_keys"] = int(
        bounded([stock, "--copy-kv", headerpath, vocab], private, "copy-metadata", r)
    )
    r.update(
        vocab_copy_sha256=sha(vocab.read_bytes()),
        vocab_copy_bytes=vocab.stat().st_size,
        source_tensor_descriptors=687,
        copied_tensors=0,
    )
    h = historical.historical
    official = historical.read(
        a.historical_results / h.ROOT_NAME / "raw" / (h.RUN_ID + ".tokenization.json"),
        manifest["tokenizations_sha256"],
    )
    reference = [official[k] for k in historical.IDS]
    expected = {"C269": rendered["C269"], "stock": rendered["stock"] + rendered["bound"]}
    results = {}
    for name, exe in (("C269", ref), ("stock", stock)):
        blob = b"".join(struct.pack("<I", len(s)) + s for s in expected[name])
        data = fields(bounded([exe, "--tokenize", vocab], private, name + "-ids", r, blob))
        check(len(data) == 1 + len(expected[name]), "missing tokenizer output")
        r["embedded_template_sha256"][name] = sha(data[0])
        for field in data[1:]:
            check(len(field) % 4 == 0, "incomplete ID")
        results[name] = [
            list(struct.unpack("<" + "i" * (len(field) // 4), field)) for field in data[1:]
        ]
    r["turns"] = []
    for i in range(2):
        ids, raw, dated = results["C269"][i], results["stock"][i], results["stock"][2 + i]
        r["turns"].append(
            {
                "turn": i + 1,
                "historical_tokens": len(reference[i]),
                "c269_count": len(ids),
                "stock_original_count": len(raw),
                "stock_dated_count": len(dated),
                "c269_equal": ids == reference[i],
                "stock_dated_equal": dated == reference[i],
                "stock_original_equal": raw == reference[i],
                "c269_ids_sha256": historical.digest(ids),
                "stock_original_ids_sha256": historical.digest(raw),
                "stock_dated_ids_sha256": historical.digest(dated),
                "stock_original_unequal_positions_and_unmatched_tail": sum(
                    x != y for x, y in zip(raw, reference[i], strict=False)
                )
                + abs(len(raw) - len(reference[i])),
            }
        )
    r["historical_prompt_common_prefix"] = next(
        (i for i, (x, y) in enumerate(zip(*reference, strict=False)) if x != y),
        min(map(len, reference)),
    )
    check(
        all(v == ORIGINAL for v in r["embedded_template_sha256"].values()),
        "embedded GGUF template differs",
    )
    check(
        all(
            t["c269_equal"] and t["stock_dated_equal"] and not t["stock_original_equal"]
            for t in r["turns"]
        ),
        "official full vectors",
    )
    check(sum(p.stat().st_size for p in private.iterdir()) <= 40 * MIB, "output budget")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for name in (
        "stock-source",
        "stock-bin",
        "c269-source",
        "c269-bin",
        "historical-results",
        "render-workspace",
        "placement",
        "window",
        "private-workspace",
        "new-output-dir",
    ):
        ap.add_argument("--" + name, type=Path, required=True)
    args = ap.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir()
    r = {
        "status": "FAIL_PRESERVED",
        "children": {},
        "libraries_sha256": {},
        "executables_sha256": {},
        "embedded_template_sha256": {},
        "model_forwards": 0,
        "cache_observed": "NOT_RUN",
        "product_response": "NOT_RUN",
        "prior_render_receipt_sha256": PRIOR,
        "sources_sha256": {
            p.name: sha(p.read_bytes())
            for p in [HERE / "protocol.md", HERE / "probe.cpp", Path(__file__)]
        },
    }
    try:
        run(args, r)
        r["status"] = "PASS_OFFICIAL_VOCAB_ONLY"
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
        r["error"] = str(exc)
    with (args.new_output_dir / "receipt.json").open("x") as f:
        json.dump(r, f, indent=2, sort_keys=True)
        f.write("\n")
    print(r["status"], r.get("error", ""))
    raise SystemExit(int(r["status"] != "PASS_OFFICIAL_VOCAB_ONLY"))
