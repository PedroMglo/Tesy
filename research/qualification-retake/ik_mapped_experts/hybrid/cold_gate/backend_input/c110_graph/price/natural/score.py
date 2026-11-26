"""Price the lifetime of exact bank input ranges using the pinned ik planner on natural routes."""

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
G = run_path(str(HERE.parent / "grade.py"))
H = G["PARENT"]["HYBRID"]
CL = H / "natural_link/classlru"
S = run_path(str(CL / "score.py"))
BASE, PAGES, FULL, sha, need = (S[k] for k in ("BASE", "PAGES", "FULL", "sha", "need"))
CAP = G["PARENT"]["CAPACITY"]
PAGE = 4096
STRIDE = 4406400
ROLES = ("gate", "up", "down")
PRIOR = "8dd73ee6625e0d7dc2e93f2f6cf919c390fad6eb5d91391e06f89ddd2db588db"
INPUT = "b776c80f0357339cfb6b588369bf63b3503f680d84b882f91deff46292da25e3"


def aligned_size(file, n):
    return (file % PAGE + n + PAGE - 1) // PAGE * PAGE


def runs(fills):
    result = []
    for expert, slot in fills:
        if result and (expert, slot) == (
            result[-1][0] + result[-1][2],
            result[-1][1] + result[-1][2],
        ):
            result[-1][2] += 1
        else:
            result.append([expert, slot, 1])
    return result


def service(layer, fills, tensors):
    spans = runs(fills)
    for role in ROLES:
        key = f"blk.{layer}.ffn_{role}_exps.weight"
        base, size, _ = tensors[key]
        need(size == 128 * STRIDE, "weight geometry")
        for expert, slot, len_experts in spans:
            yield (
                f"moe_cache.blk.0.ffn_{role}_exps.weight",
                base + expert * STRIDE,
                slot * STRIDE,
                len_experts * STRIDE,
            )


def lifetime(slices, cap):
    used, peak, drains, largest = 0, 0, 0, 0
    for _, file, _, n in slices:
        amt = aligned_size(file, n)
        need(0 < amt <= cap, "one SET exceeds scratch")
        if used + amt > cap:
            drains += 1
            used = 0
        used += amt
        peak += amt
        largest = max(largest, amt)
    return peak, drains, largest


def encode(sites):
    lines = [
        str(len(sites)),
        *(" ".join(map(str, [il, len(ids) // 4, *ids])) for _, _, _, il, ids in sites),
    ]
    return ("\n".join(lines) + "\n").encode()


def native(exe, sites, tensors, physical=None):
    data = encode(sites)
    proc = subprocess.run(
        [exe, "classlru", "288"],
        input=data,
        capture_output=True,
        timeout=35,
        check=True,
        env=BASE["IK"]["ENV"],
    )
    rows = proc.stdout.decode().splitlines()
    need(len(rows) == len(sites), "planner did not complete")
    counts = hashlib.sha256()
    result = {}
    stream = []
    for gen, ((turn, call, tile, layer, ids), line) in enumerate(zip(sites, rows, strict=True), 1):
        nums = list(map(int, line.split()))
        hits, fills, evict = nums[:3]
        pairs = list(zip(nums[3::2], nums[4::2], strict=True))
        demand = set(ids)
        need(
            len(pairs) == fills == len(demand) - hits
            and {e for e, _ in pairs} <= demand
            and len({e for e, _ in pairs}) == len({s for _, s in pairs}) == fills,
            "unexpected decision",
        )
        counts.update(f"{hits} {fills} {evict}\n".encode())
        transfers = list(service(layer, pairs, tensors))
        peak, drains, largest = lifetime(transfers, CAP)
        if physical is not None:
            for name, file, slot, n in transfers:
                stream.append(f"SET {call} {gen} {layer} {name} {file} {slot} {n}")
            tags = ["C110"]
        else:
            tags = [v for v in S["phases"](turn, call, tile) if not v.startswith("T2_decode_call_")]
            if (turn, call) == (2, 3):
                tags.append("first_decode")
        for name in tags:
            rec = result.setdefault(
                name,
                {"counts": Counter(), "maximum_B": 0, "largest_SET_aligned_B": 0, "witness": None},
            )
            rec["counts"].update(
                sites=1,
                fills=fills,
                sets=len(transfers),
                payload_B=fills * STRIDE * 3,
                sites_over=int(peak > CAP),
                extra_drains=drains,
            )
            rec["largest_SET_aligned_B"] = max(rec["largest_SET_aligned_B"], largest)
            if peak > rec["maximum_B"]:
                rec.update(maximum_B=peak, witness=[turn, call, tile, layer])
    if physical is not None:
        need(stream == physical, "native C110 run/offset/slot stream differs")
    return result, counts.hexdigest(), hashlib.sha256(data).hexdigest()


def build(ik, lib, out):
    b = BASE["IK"]
    need(b["revision"](ik) == [b["PIN"], b["TREE"]], "ik pin")
    b["require_clean"](ik)
    need(
        sha(ik / "src/llama-moe-cache-policy.h") == BASE["HDR"]
        and sha(ik / "src/llama-moe-cache.cpp") == BASE["HOOK"]
        and sha(lib) == BASE["LIB"],
        "planner authority",
    )
    src = CL / "plan.cpp"
    need(
        sha(src) == "64a3c325ecbe40fcc13b94a30748d1e4c51a94d2eabba045a199c4a41e62dd4c",
        "planner source",
    )
    code = src.read_text()

    def replace(old, new):
        nonlocal code
        need(code.count(old) == 1, "planner anchor")
        code = code.replace(old, new)

    replace("cap == 128 || cap == 161", "cap == 288")
    replace(
        "<< evictions << '\\n';",
        "<< evictions;\n        for (auto f : fills) std::cout << ' ' << f.expert"
        " << ' ' << f.slot;\n        std::cout << '\\n';",
    )
    source = out / "plan.cpp"
    source.write_text(code)
    exe = out / "plan"
    cc = Path("/usr/bin/c++")
    argv = [
        str(cc),
        "-std=c++17",
        "-O1",
        *["-I" + str(ik / v) for v in ("include", "ggml/include", "src")],
        str(source),
        str(lib),
        "-Wl,-rpath," + str(lib.parent),
        "-o",
        str(exe),
    ]
    subprocess.run(argv, check=True, env=b["ENV"], timeout=30)
    need(f"libggml.so => {lib} " in b["output"](["ldd", str(exe)]), "runtime binding")
    return exe, dict(
        compiler=sha(cc.resolve()),
        generated=sha(source),
        elf=sha(exe),
        cpu_library=sha(lib),
        argv=argv,
    )


def study(a):
    git = ["git", "-C", HERE]
    commit, tree = subprocess.check_output(
        [*git, "rev-parse", "HEAD", "HEAD^{tree}"], text=True
    ).splitlines()
    need(not subprocess.check_output([*git, "status", "--porcelain"]), "dirty research checkout")
    old = CL / "two_steps/result.json"
    need(sha(old) == PRIOR and sha(a.plan) == G["A"]["PLAN"], "prior results or tensor plan")
    previous = json.loads(old.read_bytes())
    tensors = G["PARENT"]["G"]["CAP"]["tensor_plan"](a.plan)
    exe, compiled = build(a.ik.resolve(), a.lib.resolve(), a.new_output_dir)
    heavy, logits = G["reference"](a.numerical)
    expected = [line for line in heavy.splitlines() if line.startswith("SET ")]
    control = []
    for row in heavy.splitlines():
        if row.startswith("IDS "):
            phase, gen, *ids = map(int, row.split()[1:])
            control.append((0, phase, 1, (gen - 1) % 36, ids))
    restored, _, _ = native(exe, control, tensors, expected)
    need(
        restored["C110"]["maximum_B"] == CAP and restored["C110"]["counts"]["extra_drains"] == 0,
        "C110 scratch",
    )
    ranks, geom, _, sources = PAGES["reopen"](a.p97, a.p106)
    path = a.p106 / "ON/observer/events.pfj"
    cut, _ = FULL["metadata"](path, True)
    sites, initial = S["t1_sites"](FULL["iter_rows"](path, 0, cut), FULL["T1"])
    sites.extend((2, *k, [v % 128 for v in keys]) for k, keys in BASE["flatten"](ranks, geom))
    natural, census, selector = native(exe, sites, tensors)
    need(
        selector == INPUT
        and census == previous["per_site_sha256"]["classlru_288"]
        and sum(initial.values()) == 1440,
        "natural ranks or native census",
    )
    for name in ("T1", "T2", "T2_prefill", "T2_decode", "T2_through_first_final"):
        need(
            natural[name]["counts"]["payload_B"]
            == previous["phases"]["classlru_288"][name]["payload_B"],
            "previous phase",
        )
    whole = natural["session"]
    return dict(
        decision="GO_BOUNDED_SCRATCH_FIXTURE"
        if whole["counts"]["sites_over"]
        else "KEEP_EXISTING_SCRATCH",
        evidence="TRACE_DERIVED",
        commit=commit,
        tree=tree,
        protocol_sha256=sha(HERE / "protocol.md"),
        method_sha256=sha(Path(__file__)),
        c110=restored["C110"],
        natural=natural,
        scratch_B=CAP,
        worst_case_B=3 * 128 * aligned_size(PAGE - 1, STRIDE),
        natural_input_sha256=selector,
        native_census_sha256=census,
        previous_sha256=PRIOR,
        c110_sha256=G["FAMILY"],
        c110_rows=logits,
        sources=sources,
        build=compiled,
        model_starts=0,
        http_requests=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("p97", "p106", "numerical", "plan", "ik", "lib", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        r = study(a)
    except Exception as ex:
        r = dict(decision="FAIL_PRESERVED", reason=f"{type(ex).__name__}: {ex}", model_starts=0)
    (a.new_output_dir / "receipt.json").write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
    print(r["decision"], r.get("reason", ""))
    raise SystemExit(r["decision"] == "FAIL_PRESERVED")
