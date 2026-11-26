"""Apply both pinned ik replacement policies to the complete, authenticated T1 and T2."""

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
BASE = run_path(str(HERE.parent / "score.py"))
PAGES, IK = BASE["PAGES"], BASE["IK"]
FULL = PAGES["PRED"]["PROFILE"]
need, sha = BASE["need"], BASE["sha"]
PREVIOUS = "4ea1270383e0876a709139b9dbc19c2c4244c6d976056494f08034b4a2f1adac"


def build(a):
    ik, lib = a.ik.resolve(), a.lib.resolve()
    need(IK["revision"](ik) == [IK["PIN"], IK["TREE"]], "wrong policy pin")
    IK["require_clean"](ik)
    headers = [ik / "src/llama-moe-cache-policy.h", ik / "src/llama-moe-cache.cpp"]
    need(
        [sha(p) for p in headers] == [BASE["HDR"], BASE["HOOK"]] and sha(lib) == BASE["LIB"],
        "header/hook/library mismatch",
    )
    exe = a.new_output / "plan"
    compiler = Path("/usr/bin/c++")
    cmd = [
        str(compiler),
        "-std=c++17",
        "-O1",
        *["-I" + str(ik / p) for p in ("include", "ggml/include", "src")],
        str(HERE / "plan.cpp"),
        str(lib),
        "-Wl,-rpath," + str(lib.parent),
        "-o",
        str(exe),
    ]
    subprocess.run(cmd, check=True, env=IK["ENV"], timeout=30)
    need(f"libggml.so => {lib} " in IK["output"](["ldd", str(exe)]), "wrong linked library")
    return dict(
        status="BUILT_CLASSLRU_AND_LRU",
        ik_commit=IK["PIN"],
        ik_tree=IK["TREE"],
        source_sha256=sha(HERE / "plan.cpp"),
        compiler_sha256=sha(compiler.resolve()),
        binary_sha256=sha(exe),
        hook_sha256=BASE["HOOK"],
        header_sha256=BASE["HDR"],
        lib=str(lib),
        library_sha256=sha(lib),
    )


def t1_sites(events, lengths):
    groups, counts = {}, Counter()
    previous = None
    for r in events:
        if r.kind == 5:
            counts[r.a] += 1
        if r.kind != 27:
            continue
        key = (r.call, r.tile, r.layer)
        if key != previous:
            need(key not in groups, "interleaved sites")
            groups[key] = []
            previous = key
        ids = groups[key]
        need(r.b * 4 == len(ids), "out-of-order rank row")
        ids.extend(r.a.to_bytes(4, "little"))
    expected = []
    for call, length in enumerate(lengths, 1):
        for offset in range(0, length, 32):
            tile = 1 + offset // 32
            width = min(32, length - offset)
            for il in range(36):
                n = width if il < 35 else int(call >= 9 and offset + width == length)
                if n:
                    key = (call, tile, il)
                    need(len(groups.get(key, ())) == 4 * n, "rank width/last-layer pruning")
                    expected.append(key)
    need(list(groups) == expected, "site order or unaccounted layer")
    return [(1, *k, v) for k, v in groups.items()], counts


def phases(turn, call, tile):
    if turn == 1:
        return ["session", "T1", "T1_prefill" if call <= 9 else "T1_decode"]
    tags = ["session", "T2"]
    if call <= 2:
        tags += ["T2_prefill", f"T2_prefill_{call}_{tile}"]
    else:
        tags += ["T2_decode", f"T2_decode_call_{call}"]
    if call <= 46:
        tags += ["T2_through_first_final"]
    return tags


def trial(exe, name, cap, sites, encoded):
    proc = subprocess.run(
        [exe, name, str(cap)],
        input=encoded,
        stdout=subprocess.PIPE,
        check=True,
        timeout=30,
        env=IK["ENV"],
    )
    lines = proc.stdout.decode().splitlines()
    need(len(lines) == len(sites), "incomplete native replay")
    totals, fills_by_site = {}, []
    for (turn, call, tile, _, ids), line in zip(sites, lines, strict=True):
        hits, fills, evictions = map(int, line.split())
        need(
            min(hits, fills, evictions) >= 0 and fills + hits == len(set(ids)),
            "demand conservation",
        )
        fills_by_site.append(fills)
        for phase in phases(turn, call, tile):
            totals.setdefault(phase, Counter()).update(
                sites=1,
                routed_rows=len(ids) // 4,
                hits=hits,
                fills=fills,
                evictions=evictions,
                payload_B=fills * BASE["PAYLOAD"],
            )
    need(totals["session"]["fills"] - totals["session"]["evictions"] == cap, "terminal occupancy")
    clocks = {
        k: BASE["prices"](totals[k]["fills"], n, d)
        for k, n, d in [("T2_through_first_final", 10, 1), ("T2_decode", 47, 6)]
    }
    decode = [totals.pop(f"T2_decode_call_{i}")["fills"] for i in range(3, 49)]
    return dict(
        phases=totals,
        clocks=clocks,
        decode_fills_in_call_order=decode,
        per_site_census_sha256=hashlib.sha256(proc.stdout).hexdigest(),
    ), fills_by_site


def compare(sites, left, right):
    # Positive signed fills are saved by the second policy or larger capacity.
    result = {}
    for site, x, y in zip(sites, left, right, strict=True):
        turn, call, tile, _, _ = site
        for key in phases(turn, call, tile):
            if key.startswith("T2_decode_call_"):
                continue
            c = result.setdefault(key, Counter())
            c.update(
                saved_fills=x - y,
                saved_payload_B=(x - y) * BASE["PAYLOAD"],
                fewer_sites=int(x > y),
                more_sites=int(x < y),
                equal_sites=int(x == y),
            )
    return result


def study(a):
    exe = a.build_dir / "plan"
    receipt = a.build_dir / "receipt.json"
    need(sha(receipt) == a.build_sha256, "build receipt")
    b = json.loads(receipt.read_bytes())
    need(
        b["status"] == "BUILT_CLASSLRU_AND_LRU"
        and b["ik_commit"] == IK["PIN"]
        and b["source_sha256"] == sha(HERE / "plan.cpp")
        and b["binary_sha256"] == sha(exe)
        and sha(Path(b["lib"])) == b["library_sha256"] == BASE["LIB"],
        "native build",
    )
    prev = HERE.parent / "result.json"
    need(sha(prev) == PREVIOUS, "previous LRU control")
    previous = json.loads(prev.read_bytes())
    ranks, geom, _, sources = PAGES["reopen"](a.p97, a.p106)
    need((len(geom), len(ranks)) == (48, 7012), "T2 geometry")
    _, _, http, audit = PAGES["CHAIN"]["chain"](a.p97, PAGES["P97"])
    need(
        audit["http_cut"]["sample_number"] == 45
        and audit["http_cut"]["sample_call"] == 46
        and http["rows"][1]["predicted_n"] == 47,
        "T2 clock",
    )
    path = a.p106 / "ON/observer/events.pfj"
    cut, _ = FULL["metadata"](path, True)
    seal = json.loads((a.p106 / "ON/before-t2.json").read_bytes())
    need(
        seal["records"] == cut and seal["ranks"] == 74278 and seal["last_position"] == 2119,
        "T1 prefix",
    )
    sites, initial = t1_sites(FULL["iter_rows"](path, 0, cut), FULL["T1"])
    need(
        sum(len(s[-1]) for s in sites) == 4 * 74278 and sum(initial.values()) == 1440,
        "T1 routed rows/initial Tesy snapshot",
    )
    sites += [(2, *k, [v % 128 for v in keys]) for k, keys in BASE["flatten"](ranks, geom)]
    lines = [str(len(sites))]
    lines.extend(" ".join(map(str, [il, len(ids) // 4, *ids])) for _, _, _, il, ids in sites)
    encoded = ("\n".join(lines) + "\n").encode()
    results, series = {}, {}
    for cap in (128, 161):
        for name in ("lru", "classlru"):
            key = f"{name}_{cap}"
            results[key], series[key] = trial(exe, name, cap, sites, encoded)
        old = previous["budgets"][str(cap)]["decode_fills_by_call_3_to_48"]
        need(results[f"lru_{cap}"]["decode_fills_in_call_order"] == old, "historical LRU drift")
    pairs = {}
    for tag, left, right in [
        ("policy_128", "lru_128", "classlru_128"),
        ("policy_161", "lru_161", "classlru_161"),
        ("capacity_lru", "lru_128", "lru_161"),
        ("capacity_classlru", "classlru_128", "classlru_161"),
    ]:
        pairs[tag] = compare(sites, series[left], series[right])
    return dict(
        status="TRACE_DERIVED_IK_POLICIES_AFTER_OBSERVED_T1",
        build_sha256=a.build_sha256,
        method_sha256=sha(Path(__file__)),
        protocol_sha256=sha(HERE / "protocol.md"),
        sources=sources
        | {"previous_LRU": PREVIOUS, "t1_prefix": seal["sha256"], "t1_route": seal["route_sha256"]},
        native_input_sha256=hashlib.sha256(encoded).hexdigest(),
        initial_Tesy_slot_state_counts=dict(initial),
        initial_ik="assumed_empty_prior_to_T1",
        payload_B=BASE["PAYLOAD"],
        link_gross_B_s=BASE["CEILING"],
        results=results,
        paired=pairs,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    for action, args in [("build", ["ik", "lib"]), ("study", ["p97", "p106", "build-dir"])]:
        q = sub.add_parser(action)
        for k in [*args, "new-output"]:
            q.add_argument("--" + k, required=True, type=Path)
        if action == "study":
            q.add_argument("--build-sha256", required=True)
    a = p.parse_args()
    a.new_output.mkdir(mode=0o700, exist_ok=False)
    try:
        result = build(a) if a.action == "build" else study(a)
    except Exception as exc:
        result = {"status": "FAIL_PRESERVED", "error": str(exc)}
    tmp = a.new_output / ".pending"
    with tmp.open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.rename(a.new_output / "receipt.json")
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
