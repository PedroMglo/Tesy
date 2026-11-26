"""Shape-only native C291 CPU router calibration on C270 activation windows."""

import argparse
import ctypes as ct
import hashlib
import json
import os
import resource
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from runpy import run_path
from statistics import median

import numpy as np

HERE = Path(__file__).resolve().parent
OP = run_path(str(HERE.parent / "run.py"))
BASE, P, TF, need, sha = (OP[k] for k in ("BASE", "P", "TF", "need", "digest"))
ROW = BASE.parent / "history_lookup/b3_numeric/first_boundary/router_row"
ROW_SHA = "b2ad2fd6e893c85986af58949af84a879e42836dc6d255bbd973c4b9884d733e"
CLOSURE = "9e553bcfa3dd8889100c8836bc3b873491248567672f93e7859e7f8b76e35116"
METHOD = "7bddc888d1dd94e22d0bc67606b50048de802d4fe72fb234436250199bf4579c"
WINDOWS = {32: slice(0, 32), 5: slice(0, 5), 20: slice(12, 32)}
PHASES = ("prefill0", "prefill128")


def build_gold(a):
    closure = json.loads(P.file(a.closure, CLOSURE))
    b = a.c7 / "backends/c269-layer-last-use"
    libs = b / "build-c269-cuda/bin"
    base = run_path(str(ROW.parents[1] / "cpu_row_geometry/run.py"))
    need(base["git"](b, "rev-parse", "HEAD") == base["COMMIT"], "C269 source pin")
    for name, h in base["PINS"].items():
        need(sha(b / name) == h, "GGML source pin")
    evidence = {}
    for name, h in base["LIBS"].items():
        soname = name.replace(".0.15.3", ".0")
        path = (libs / name).resolve()
        need(
            sha(path) == h
            and closure["startup"][soname] == {"file": str(path), "sha256": h}
            and closure["per_mode"]["on"]["server"][soname] == str(path),
            "C291 CPU providers",
        )
        evidence[soname] = h
    fixture = ROW / "fixture.cpp"
    cxx = Path("/usr/bin/g++-15")
    need(
        sha(fixture) == ROW_SHA
        and sha(cxx) == "cef5002fbce633104c81b24e9fd935251ab653234c8dce8758d3c963d6123c8a",
        "graph and compiler",
    )
    binary = a.new_output_dir / "native-widths"
    subprocess.run(
        [
            cxx,
            "-std=c++17",
            "-O2",
            "-fPIC",
            "-pie",
            "-fno-plt",
            f'-DTESY_ROUTER_ROW_FIXTURE="{fixture}"',
            "-I",
            b / "ggml/include",
            HERE / "native.cpp",
            "-L",
            libs,
            "-lggml-cpu",
            "-lggml-base",
            "-ldl",
            "-o",
            binary,
        ],
        check=True,
        timeout=30,
    )
    return (
        binary,
        libs,
        {"providers": evidence, "native_sha256": sha(binary), "frame_sha256": ROW_SHA},
    )


def replace_once(s, old, new):
    need(s.count(old) == 1, "score observer anchor")
    return s.replace(old, new)


def diagnostic(out, canonical):
    # Two write-only taps on the final biased scalar. The timed ELF remains byte-for-byte original.
    header = OP["HERE"].parent / "projector.h"
    parent = OP["HERE"] / "operator.cpp"
    need(
        sha(header) == OP["PJ"]
        and sha(parent) == "0e06a74a4745273c122e263aed83f969fe5eaa578d3dfc915b73e6161f1d90b7",
        "resident sources",
    )
    capture = "static float *watch; static int used;\n"
    h = replace_once(
        header.read_text(),
        "sum+=bias[i]; finite(sum);",
        "sum+=bias[i]; finite(sum); watch[used++]=sum;",
    )
    s = replace_once(parent.read_text(), '#include "../projector.h"', capture + h)
    s = replace_once(
        s,
        "finite(v);\n            for (int p=",
        "finite(v); watch[used++]=v;\n            for (int p=",
    )
    s += '\nextern "C" void start_observation(float *p){watch=p;used=0;}\n'
    s += 'extern "C" int end_observation(){watch=nullptr;return used;}\n'
    s = s.replace("#pragma once", "")  # header is now at file scope
    source = out / "observed.cpp"
    source.write_text(s)
    elf = out / "observed.so"
    subprocess.run(
        [
            OP["CXX"],
            "-std=gnu++17",
            "-O3",
            "-DNDEBUG",
            "-fPIC",
            "-shared",
            source,
            OP["BLAS"],
            "-Wl,-rpath," + str(OP["BLAS"].parent),
            "-o",
            elf,
        ],
        check=True,
        timeout=30,
    )
    obs = ct.CDLL(str(elf))
    obs.site.argtypes = canonical.argtypes
    obs.site.restype = canonical.restype
    obs.start_observation.argtypes = [np.ctypeslib.ndpointer(dtype="<f4", flags="C_CONTIGUOUS")]
    obs.start_observation.restype = None
    obs.end_observation.argtypes = []
    obs.end_observation.restype = ct.c_int
    return obs


def real_rows(args, binary, libs, phase, layer, row, params):
    backend = args.c7 / "results" / P.C299 / "raw/c299-code153-2-estimate.native"
    params_folder = backend if 2 <= layer <= 24 else args.bundle / "parameters"
    paths = [params_folder / f"blk.{layer}.ffn_gate_inp.{role}.f32" for role in ("weight", "bias")]
    for path, arr in zip(paths, params[layer][1:], strict=True):
        need(sha(path) == hashlib.sha256(arr.tobytes()).hexdigest(), "native matrix or bias")
    x = row["attn_post_norm"]
    need(x.shape == (32, 2880), "parent activation shape")
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "OMP_NUM_THREADS": "8",
        "OMP_DYNAMIC": "FALSE",
        "OMP_THREAD_LIMIT": "8",
        "LD_LIBRARY_PATH": str(libs),
        "CUDA_VISIBLE_DEVICES": "",
    }
    with tempfile.TemporaryDirectory(dir=args.new_output_dir) as t:
        out = Path(t) / "graphs"
        run = subprocess.run(
            [binary, *paths, out],
            input=x.tobytes(),
            env=env,
            capture_output=True,
            check=True,
            timeout=12,
        )
        records = run.stdout.decode().splitlines()
        need(
            records
            == [
                f"cpu {(libs / 'libggml-cpu.so.0.15.3').resolve()}",
                f"base {(libs / 'libggml-base.so.0.15.3').resolve()}",
                *[f"w{n} 0 0 0 0 0" for n in WINDOWS],
            ],
            f"active CPU provider {phase}/{layer}",
        )
        result = {}
        for n in WINDOWS:
            block = {}
            for name, width, dtype in (
                ("logits", 128, "<f4"),
                ("biased", 128, "<f4"),
                ("ids", 4, "<i4"),
                ("mix", 4, "<f4"),
            ):
                path = out / f"w{n}.{name}"
                need(path.stat().st_size == n * width * 4, "graph output length")
                a = np.frombuffer(path.read_bytes(), dtype=dtype).reshape(n, width)
                need(np.isfinite(a).all(), "finite native output")
                block[name] = a
            need(np.array_equal(P.ranks(block["biased"]), block["ids"]), "native sorted IDs")
            need(
                np.array_equal(
                    (block["logits"] + params[layer][2]).view("<u4"), block["biased"].view("<u4")
                ),
                "native bias",
            )
            result[n] = block
    return result


def diff(ref, other):
    need(
        ref.shape == other.shape and np.isfinite(other).all() and ref.dtype == other.dtype,
        "observable finite shape/types",
    )
    return dict(
        words=ref.size,
        unequal_bits=int((ref.view("<u4") != other.view("<u4")).sum()),
        max_abs=float(np.max(np.abs(ref.astype("f8") - other))),
    )


def add(cell, metric, ref, actual):
    now = diff(ref, actual)
    current = cell.setdefault(metric, {"words": 0, "unequal_bits": 0, "max_abs": 0.0})
    current["words"] += now["words"]
    current["unequal_bits"] += now["unequal_bits"]
    current["max_abs"] = max(current["max_abs"], now["max_abs"])
    return now


def case(phase, layer, offset, x, source_gamma, dest_gamma, w, b, ids, occupied):
    n = len(x)
    occ = np.zeros(128, dtype="u1")
    for e in occupied:
        occ[e] = 1
    selected, _ = OP["M"]["choose"](ids, occupied, 4)
    offers = np.array(selected + [-1] * (4 - len(selected)), dtype="<i4")
    inputs = (layer, n, x, source_gamma, dest_gamma, w, b, np.ones(n, dtype="u1"), occ)
    return (phase, layer, offset, None, 0, {}, ids, offers, inputs)


def study(a, rec):
    need(
        sha(HERE / "protocol.md") == METHOD
        and resource.getrlimit(resource.RLIMIT_AS) == (1 << 29, 1 << 29),
        "protocol or AS",
    )
    health = OP["health_setup"](a.unit)
    rec["before"] = health()
    exe, libs, rec["gold_provider"] = build_gold(a)
    fn, rec["producer"] = OP["compile_native"](a.new_output_dir / "operator.so")
    need(
        rec["producer"]["elf_sha256"]
        == "b37156455c25df12cb03cadbd1b82c8c5c01f5fa96221e38a8bf7be530f5b76c",
        "canonical ELF",
    )
    obs = diagnostic(a.new_output_dir, fn)
    rec["observed_sha256"] = sha(a.new_output_dir / "observed.so")
    OP["controls"](fn)
    pos, cuts, windows = OP["observations"](a)
    rows, _, _ = P.capture(a.part23)
    mix = TF["native_mix"](a.part23, rows)
    params, _, rec["bank"] = OP["bank"](a)
    ones = np.ones(2880, dtype="<f4")
    cases = []
    cells = rec["widths"] = {}
    tokens = Counter()
    neg = False
    for phase in PHASES:
        tile = pos[P.PHASES[phase][0]]
        for layer in range(25):
            row = rows[phase, layer]
            gamma, w, b = params[layer]
            oracle = real_rows(a, exe, libs, phase, layer, row, params)
            for name, source in (
                ("logits", row["ffn_moe_logits"]),
                ("ids", row["ffn_moe_topk"]),
                ("mix", mix[phase, layer]),
            ):
                result = diff(oracle[32][name], source)
                need(result["unequal_bits"] == 0, f"known32 {phase}/{layer}/{name}: {result}")
            if not neg:
                neg = (
                    diff(oracle[32]["logits"][:2], row["ffn_moe_logits"][:2][::-1])["unequal_bits"]
                    > 0
                )
                need(neg, "wrong-order negative")
            for n, sl in WINDOWS.items():
                block = oracle[n]
                cell = cells.setdefault(str(n), {})
                tokens[n] += n
                for name in ("logits", "biased", "ids", "mix"):
                    add(cell, "native_vs_slice_" + name, block[name], oracle[32][name][sl])
                cal = case(
                    phase,
                    layer,
                    0,
                    row["attn_post_norm"][sl],
                    ones,
                    ones,
                    w,
                    b,
                    block["ids"],
                    set(),
                )
                for mode, label in enumerate(("scalar", "blas")):
                    OP["call"](fn, cal, mode, False)
                    scores = np.empty((n, 128), dtype="<f4")
                    obs.start_observation(scores)
                    OP["call"](obs.site, cal, mode, False)
                    need(
                        obs.end_observation() == n * 128
                        and np.array_equal(P.ranks(scores), block["ids"]),
                        "score observer conservation",
                    )
                    ds = add(cell, label + "_scores", block["biased"], scores)
                    dm = add(
                        cell,
                        label + "_mix",
                        block["mix"],
                        TF["native_order_softmax"](scores, block["ids"]),
                    )
                    need(
                        ds["max_abs"] <= 1e-4 and dm["max_abs"] <= 1e-5,
                        f"score/mix tolerance: {phase}/{layer}/{n}/{label}",
                    )
                if layer == 0:
                    continue
                xsrc = rows[phase, layer - 1]["attn_post_norm"]
                src_gamma = params[layer - 1][0]
                pred = P.ranks(((xsrc / src_gamma) * gamma) @ w.T + b)[sl]
                occupied = cuts[(*tile, layer)][2]
                planned = case(phase, layer, 1, xsrc[sl], src_gamma, gamma, w, b, pred, occupied)
                for mode in (0, 1):
                    OP["call"](fn, planned, mode, False)
                if n == 32:
                    offers = [int(expert) for expert in planned[7] if expert >= 0]
                    need(offers == windows[(*tile, layer)][1], "parent ordered offers at 32")
                    continue
                hits = int((pred[:, :, None] == block["ids"][:, None, :]).any(axis=2).sum())
                cell["plus1_intersection"] = cell.get("plus1_intersection", 0) + hits
                cell["plus1_rows"] = cell.get("plus1_rows", 0) + n
                cases.append(planned)
            health()
    need(tokens == {5: 250, 20: 1000, 32: 1600} and len(cases) == 96 and neg, "populations")
    rec["calibration_rows"] = dict(tokens)
    rec["permuted_control_detected"] = neg
    rec["cpu"] = OP["cpu_pin"]()
    runs = []
    per = {5: [[], []], 20: [[], []]}
    for item in cases:
        n = len(item[6])
        for mode in (0, 1):
            OP["call"](fn, item, mode, False)
        pairs = []
        for first in OP["ORDER"]:
            pair = [0, 0]
            for mode in (first, 1 - first):
                pair[mode] = OP["call"](fn, item, mode, True)
            pairs.append(pair)
        for mode in (0, 1):
            per[n][mode].append(median([p[mode] for p in pairs]))
        runs.append([item[0], item[1], n, pairs])
        health()
    rec.update(
        status="MEASURED_NATIVE_CPU_ROUTER_WIDTHS",
        site_times_ns={
            str(n): {
                label: OP["dist"](values)
                for label, values in zip(("scalar", "blas"), both, strict=True)
            }
            for n, both in per.items()
        },
        paired_times=runs,
        after=health(),
        gguf_bytes=0,
        model_forwards=0,
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for k in ("c7", "bundle", "part23", "part95", "original", "closure", "new-output-dir"):
        ap.add_argument("--" + k, type=Path, required=True)
    ap.add_argument("--unit", required=True)
    args = ap.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir()
    rec = {
        "status": "FAIL_PRESERVED",
        "protocol_sha256": METHOD,
        "source_sha256": sha(HERE / "run.py"),
    }
    try:
        study(args, rec)
    except Exception as exc:
        rec["error"] = repr(exc)
    (args.new_output_dir / "receipt.json").write_text(
        json.dumps(rec, indent=2, sort_keys=True) + "\n"
    )
    print(rec["status"], rec.get("error", ""))
    raise SystemExit(int(rec["status"] == "FAIL_PRESERVED"))
