"""Calibrate and measure two resident router producers on the same pinned CPU."""

import argparse
import ctypes as c
import hashlib
import json
import os
import platform
import resource
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path
from statistics import median

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[2]
DL = run_path(str(BASE / "demand/deadlines/score.py"))
M, P, TF, need = (DL[k] for k in ("M", "P", "TF", "need"))
BLAS = Path(sys.prefix, "lib/python3.14/site-packages/numpy.libs/libscipy_openblas64_-f48b354e.so")
METHOD = "9db2b7049d863bc072ecfe8aa48665a21f43c6d901e46e188a8d58cf9bb0485b"
SHLIB = "432e1c1739731468ba305771af96773939e43016643e2d630f58cb45b6670e96"
CXX = Path("/usr/bin/c++")
PJ = "0d58291534aa84b66de887a816069451628ef7ad33a313abd10b95b10dc1eb22"
CAP = 1 << 30
ORDER = (0, 1, 0, 1, 1, 0, 1, 0)
PRICE = DL["WINDOW"] * 10**9


def digest(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def compile_native(path):
    need(
        digest(BLAS) == SHLIB and digest(HERE.parent / "projector.h") == PJ,
        "compiled operator inputs",
    )
    need(
        digest(CXX) == "ca48a2d27d0796399adc3387225eec4be62974e26fa299710edfde0c1af5aa63",
        "compiler",
    )
    cmd = [
        str(CXX),
        "-std=gnu++17",
        "-O3",
        "-DNDEBUG",
        "-fPIC",
        "-shared",
        str(HERE / "operator.cpp"),
        str(BLAS),
        "-Wl,-rpath," + str(BLAS.parent),
        "-o",
        str(path),
    ]
    subprocess.run(cmd, check=True, timeout=30)
    so = c.CDLL(str(path))
    library = c.CDLL(str(BLAS))
    th = library.scipy_openblas_get_num_threads64_
    th.restype = c.c_int
    need(th() == 1, "OpenBLAS threads")
    name = library.scipy_openblas_get_corename64_
    name.restype = c.c_char_p
    f = np.ctypeslib.ndpointer(dtype="<f4", flags="C_CONTIGUOUS")
    i = np.ctypeslib.ndpointer(dtype="<i4", flags="C_CONTIGUOUS")
    u = np.ctypeslib.ndpointer(dtype="u1", flags="C_CONTIGUOUS")
    fn = so.site
    fn.argtypes = [c.c_int] * 4 + [f] * 5 + [u, u, i, i, c.POINTER(c.c_uint64)]
    fn.restype = c.c_int
    maps = Path("/proc/self/maps").read_text()
    providers = {line.split()[-1] for line in maps.splitlines() if "openblas" in line}
    need(providers == {str(BLAS.resolve())}, "BLAS mapping")
    return fn, dict(
        elf_sha256=digest(path),
        compiler_sha256=digest(CXX),
        blas_sha256=SHLIB,
        blas_core=name().decode(),
        threads=th(),
        source_sha256=digest(HERE / "operator.cpp"),
    )


def health_setup(unit):
    roots = [
        x
        for x in Path("/sys/class/hwmon").glob("hwmon*/temp*_label")
        if x.read_text().strip() == "Tctl"
    ]
    need(len(roots) == 1, "AMD Tctl sensor")
    tg = roots[0].with_name(roots[0].name.replace("_label", "_input"))
    cg = Path("/sys/fs/cgroup" + Path("/proc/self/cgroup").read_text().strip().split("::")[1])
    need(
        cg.name == unit + ".scope"
        and (cg / "memory.max").read_text().strip() == str(CAP)
        and (cg / "memory.swap.max").read_text().strip() == "0",
        "scope caps",
    )

    def health():
        ac = int(Path("/sys/class/power_supply/AC0/online").read_text())
        temp = int(tg.read_text())
        events = dict(line.split() for line in (cg / "memory.events").read_text().splitlines())
        swap = int((cg / "memory.swap.current").read_text())
        need(
            ac == 1
            and temp < 95000
            and swap == 0
            and all(int(events[k]) == 0 for k in ("oom", "oom_kill", "max")),
            "power, temperature or scope",
        )
        return dict(
            ac=ac,
            cpu_mC=temp,
            cgroup_peak_bytes=int((cg / "memory.peak").read_text()),
            swap_bytes=swap,
        )

    return health


def cpu_pin():
    eligible = sorted(os.sched_getaffinity(0))

    def freq(n):
        return int(Path(f"/sys/devices/system/cpu/cpu{n}/cpufreq/cpuinfo_max_freq").read_text())

    core = max(eligible, key=freq)
    os.sched_setaffinity(0, {core})
    need(os.sched_getaffinity(0) == {core}, "single CPU")
    return dict(
        logical_cpu=core,
        cpuinfo_max_khz=freq(core),
        kernel=platform.release(),
        model=next(
            x.split(":", 1)[1].strip()
            for x in Path("/proc/cpuinfo").read_text().splitlines()
            if x.startswith("model name")
        ),
    )


def bank(args):
    parent = json.loads(P.file(BASE / "tf32/receipt.json", M["CAL"]))
    start = time.monotonic_ns()
    params = TF["parameters"](args.c7, args.bundle, parent["weights_sha256"])
    sources_ns = time.monotonic_ns() - start
    t = time.monotonic_ns()
    for g, w, b in params:
        need(
            np.isfinite(w).all()
            and np.isfinite(g).all()
            and np.isfinite(b).all()
            and (g != 0).all(),
            "finite bank",
        )
    check_ns = time.monotonic_ns() - t
    t = time.monotonic_ns()
    rounded = {layer: TF["rounded"](params[layer][1]) for layer in range(25, 36)}
    rounding_ns = time.monotonic_ns() - t
    for g, w, b in params:
        for v in (g, w, b):
            v.setflags(write=False)
    for w in rounded.values():
        w.setflags(write=False)
    return (
        params,
        rounded,
        dict(
            authenticate_and_load_ns=sources_ns,
            finite_checks_ns=check_ns,
            rounded_construction_ns=rounding_ns,
            cpu_tier_parameters_bytes=sum(a.nbytes for p in params[:25] for a in p),
            cuda_tier_host_parameters_bytes=sum(a.nbytes for p in params[25:] for a in p),
            cuda_tier_rounded_bank_bytes=sum(w.nbytes for w in rounded.values()),
            blas_persistent_scratch_bytes=(2880 + 128) * 32 * 4,
            scalar_header_lhs_bytes=2880 * 4,
        ),
    )


def observations(args):
    dl, _, _ = DL["collect"](args)
    # Discard the previous scorer's gate matrix cache before creating the operator bank.
    P.project = None
    path = args.part95 / "tesy-c292-pack-numeric-physical-20261125-r02/overlay_on/raw/phase.pfj1"
    events, head = M["AUDIT"]["read_journal"](path)
    need(head["journal_sha256"] == M["JOURNAL"], "C292 journal")
    tiles, _, _, cuts, _, _, _ = M["journal"](events)
    release_to_site = {v[0]: k for k, v in cuts.items()}
    windows = {release_to_site[ix]: (g, offered, hits, r) for ix, r, g, offered, hits in dl}
    return {bounds[0]: key for key, bounds in tiles.items()}, cuts, windows


def geometry(args, rec):
    pos, cuts, windows = observations(args)
    rows, _, _ = P.capture(args.part23)
    params, rounded, rec["bank"] = bank(args)
    # Reference is external to both measured producers and is released after calibration.
    reference = TF["surrogate"](params)
    old = json.loads(
        P.file(
            HERE.parent / "result.json",
            "5291f0b48158637c35e9afa9344a83376c95cf1477408a6b50a3b54a54ff1709",
        )
    )
    need(
        old["archive_calibration"]["reference_rows"] == 3400
        and old["archive_calibration"]["reference_order_mismatches"] == 0
        and all(
            v["order_mismatches_vs_surrogate"] == 0
            for v in old["archive_calibration"]["forecast"].values()
        ),
        "prior compiled rank witness",
    )
    ones = np.ones(2880, dtype="<f4")
    cases = []
    for (phase, layer), gold in sorted(
        rows.items(), key=lambda kv: (P.PHASES[kv[0][0]][0], kv[0][1])
    ):
        gamma, weights, bias = params[layer]
        official = gold["ffn_moe_topk"]
        size = len(official)
        matrix = rounded[layer] if layer >= 25 and size in (29, 32) else weights
        for offset in range(1 + int(layer > 0)):
            src = rows[phase, layer - offset]
            x = src["attn_post_norm"]
            start = gold["start"] - src["start"]
            mask = np.zeros(len(x), dtype="u1")
            need(0 <= start < start + size <= len(x), "source mask")
            mask[start : start + size] = 1
            chosen = x[start : start + size]
            sg, dg = (params[layer - 1][0], gamma) if offset else (ones, ones)
            expected = (
                P.ranks(reference((chosen / sg) * dg, weights, bias)[1]) if offset else official
            )
            occ = np.zeros(128, dtype="u1")
            group, limit, release = None, {}, 0
            if offset:
                site = (*pos[P.PHASES[phase][0]], layer)
                group, limited, limit, release = windows[site]
                for e in cuts[site][2]:
                    occ[e] = 1
            offers, _ = M["choose"](expected, {i for i in range(128) if occ[i]}, 4)
            if offset:
                need(offers == limited, "original four causal offers")
            expected_offers = np.array(offers + [-1] * (4 - len(offers)), dtype="i4")
            cases.append(
                (
                    phase,
                    layer,
                    offset,
                    group,
                    release,
                    limit,
                    expected,
                    expected_offers,
                    (layer, len(x), x, sg, dg, matrix, bias, mask, occ),
                )
            )
    return cases


def call(fn, case, mode, timed):
    phase, layer, offset, _, _, _, expected, offers, inputs = case
    output = np.empty_like(expected, dtype="<i4", order="C")
    actual = np.empty(4, dtype="<i4")
    ns = c.c_uint64(0)
    n = fn(mode, int(timed), *inputs, output, actual, c.byref(ns))
    mismatches = int(np.any(output != expected, axis=1).sum()) if n == len(expected) else -1
    need(
        n == len(expected) and mismatches == 0 and np.array_equal(actual, offers),
        f"ranks/offers: phase={phase} layer={layer} offset={offset} rows={len(expected)} "
        f"mode={mode} differing_rows={mismatches}",
    )
    return ns.value


def controls(fn):
    matrix = np.zeros((128, 2880), dtype="<f4")
    matrix[:, 0] = np.arange(128)
    gamma = np.ones(2880, dtype="<f4")
    bias = np.zeros(128, dtype="<f4")
    mask = np.array([0, 1], dtype="u1")
    occupied = np.zeros(128, dtype="u1")
    occupied[[0, 127]] = 1
    for sign, ranks, expected_offers in (
        (1, [127, 126, 125, 124], [124, 125, 126, -1]),
        (-1, [0, 1, 2, 3], [1, 2, 3, -1]),
        (0, [0, 1, 2, 3], [1, 2, 3, -1]),
    ):
        x = np.zeros((2, 2880), dtype="<f4")
        x[:, 0] = [float("nan"), sign]
        inputs = (0, 2, x, gamma, gamma, matrix, bias, mask, occupied)
        case = ("control", 0, 1, None, 0, {}, np.array([ranks]), expected_offers, inputs)
        for mode in (0, 1):
            call(fn, case, mode, False)
    return {"modes": 2, "cases": 3, "nonselected_nan_skipped": True}


def dist(values):
    v = sorted(values)
    return dict(
        n=len(v),
        min=v[0],
        median=median(v),
        p10=v[(len(v) - 1) // 10],
        p90=v[9 * (len(v) - 1) // 10],
        max=v[-1],
    )


def family(args, rec):
    need(digest(HERE / "protocol.md") == METHOD, "protocol")
    need(resource.getrlimit(resource.RLIMIT_AS) == (1 << 29, 1 << 29), "512 MiB AS limit")
    health = health_setup(args.unit)
    rec.update(cpu=cpu_pin(), before=health(), start_utc_ns=time.time_ns())
    fn, rec["native"] = compile_native(args.new_output_dir / "operator.so")
    rec["synthetic_checks"] = controls(fn)
    cases = geometry(args, rec)
    census = Counter()
    for case in cases:
        for mode in (0, 1):
            call(fn, case, mode, False)
        census[case[2]] += len(case[6])
    need(census == {0: 3400, 1: 3303}, "rank populations")
    rec["calibration_rows"] = dict(census)
    cells = defaultdict(lambda: defaultdict(list))
    bridge = defaultdict(Counter)
    raw = []
    temps = [rec["before"]["cpu_mC"]]
    print("Beginning paired operator calls", flush=True)
    for case in (item for item in cases if item[2]):
        phase, layer, _, g, release, limits, *_ = case
        for mode in (0, 1):
            call(fn, case, mode, False)
        pairs = []
        for first in ORDER:
            pair = [0, 0]
            for mode in (first, 1 - first):
                pair[mode] = call(fn, case, mode, True)
            pairs.append(pair)
        s, b, delta = (
            median(v)
            for v in ([p[0] for p in pairs], [p[1] for p in pairs], [x - y for x, y in pairs])
        )
        cells[g]["scalar"].append(s)
        cells[g]["blas"].append(b)
        cells[g]["paired_scalar_minus_blas"].append(delta)
        bridge[g]["sites"] += 1
        if limits:
            bridge[g]["sites_with_hit"] += 1
            for rate in DL["PRICES"]:
                budget = min(ds[1] for ds in limits.values()) - release
                for name, t in (("free", 0), ("scalar", s), ("blas", b)):
                    bridge[g][f"{name}_{rate}"] += int(
                        (2 * budget - int(2 * t)) * rate >= 2 * PRICE
                    )
        raw.append([phase, layer, pairs])
        temps.append(health()["cpu_mC"])
    rec.update(
        status="MEASURED_RESIDENT_ROUTER_OPERATORS",
        site_times_ns={g: {k: dist(v) for k, v in d.items()} for g, d in cells.items()},
        first_due_budget=bridge,
        paired_times=raw,
        after=health(),
        temperature_range_mC=[min(temps), max(temps)],
        maxrss_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        end_utc_ns=time.time_ns(),
        gguf_bytes=0,
        model_forwards=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for n in ("c7", "part23", "part95", "bundle", "original", "new-output-dir"):
        parser.add_argument("--" + n, type=Path, required=True)
    parser.add_argument("--unit", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir()
    rec = {
        "status": "FAIL_PRESERVED",
        "method_sha256": METHOD,
        "program_sha256": digest(Path(__file__)),
    }
    try:
        family(args, rec)
    except Exception as e:
        rec["error"] = repr(e)
    body = json.dumps(rec, indent=2, sort_keys=True) + "\n"
    need(len(body) < 2 << 20, "output cap")
    (args.new_output_dir / "receipt.json").write_text(body)
    print(rec["status"], rec.get("error", ""))
    raise SystemExit(int(rec["status"] == "FAIL_PRESERVED"))
