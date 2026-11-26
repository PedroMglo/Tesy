"""Replay the pinned group LRU and bound its unknown initial state on the sealed natural T2."""

import argparse
import json
import subprocess
from collections import OrderedDict
from itertools import groupby, islice
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
PAGES = run_path(str(HERE.parents[1] / "natural_pages/score.py"))
IK = PAGES["IK"]
QUAL = HERE.parents[2]
need, sha = IK["need"], IK["sha"]
PAYLOAD, CEILING = 13_219_200, 16_000_000_000
HDR = "5b1d5df26b8f55937577ee778dd57198678c6e883175e8032e16d9f223541fe6"
HOOK = "d1371673b1d6c6097352067d55f76d9b272190f149d83e3b2a8be753dcd11dba"
LIB = "5395348a4bffef748be95e7657cbd25dd2ceaaa50f4f00e0f9d58dc742329c0c"


def build(ik, lib, out):
    need(IK["revision"](ik) == [IK["PIN"], IK["TREE"]], "wrong upstream commit/tree")
    IK["require_clean"](ik)
    need(
        sha(ik / "src/llama-moe-cache-policy.h") == HDR
        and sha(ik / "src/llama-moe-cache.cpp") == HOOK
        and sha(lib) == LIB,
        "header/hook/lib",
    )
    cmd = [
        "/usr/bin/c++",
        "-std=c++17",
        "-O1",
        *["-I" + str(ik / p) for p in ("include", "ggml/include", "src")],
        str(HERE / "plan.cpp"),
        str(lib),
        "-Wl,-rpath," + str(lib.parent),
        "-o",
        str(out / "plan"),
    ]
    subprocess.run(cmd, env=IK["ENV"], check=True, timeout=30)
    closure = IK["output"](["ldd", str(out / "plan")])
    need(f"libggml.so => {lib} " in closure, "actual CPU GGML closure")
    return {
        "status": "BUILT_IK_POLICY",
        "header_sha256": HDR,
        "hook_sha256": HOOK,
        "library_sha256": LIB,
        "compiler_sha256": sha(Path(cmd[0]).resolve()),
        "source_sha256": sha(HERE / "plan.cpp"),
        "executable_sha256": sha(out / "plan"),
        "external_pin": IK["PIN"],
        "library_path": str(lib),
    }


def logical(bank, keys, cap):
    # Oldest first; the upstream touches each hit once in first-rank order,
    # then fills the missing logical IDs in ascending expert order.
    ordered = list(dict.fromkeys(keys))
    hits = [k for k in ordered if k in bank]
    missing = sorted(set(ordered) - set(hits))
    for k in hits:
        bank.move_to_end(k)
    evicted = 0
    for k in missing:
        if len(bank) == cap:
            bank.popitem(last=False)
            evicted += 1
        bank[k] = None
    return len(hits), len(missing), evicted


def replay(exe, sites, cap, seed):
    lines = [f"{cap} {len(seed)} {len(sites)}", " ".join(map(str, seed))]
    for (_, _, layer), ids in sites:
        lines.append(f"{layer} {len(ids) // 4} " + " ".join(str(k % 128) for k in ids))
    env = IK["ENV"]
    cmd = subprocess.run(
        [exe],
        input="\n".join(lines) + "\n",
        text=True,
        stdout=subprocess.PIPE,
        check=True,
        env=env,
        timeout=20,
    )
    bank = OrderedDict.fromkeys(seed)
    need(len(bank) == len(seed) <= cap, "seed invalid")
    fills, hits, states = [], [], []
    for (_, keys), line in zip(sites, cmd.stdout.splitlines(), strict=True):
        hit, fill, evict, *native = map(int, line.split())
        need(
            (hit, fill, evict) == logical(bank, keys, cap) and native == list(bank),
            "upstream and independent logical recency differ",
        )
        hits.append(hit)
        fills.append(fill)
        states.append(tuple(native))
    return fills, hits, states


def certify(groups, cap):
    # A previously selected key is absent after at least K distinct keys were
    # touched in later groups. The same applies to an initially resident but
    # never-selected key after K distinct T2 keys. Within-group order is unknown here.
    latest = OrderedDict()
    forced, prospective_first = [], []
    streak = 0
    for i, group in enumerate(groups):
        unique = tuple(dict.fromkeys(group))
        kth = next(islice(reversed(latest.values()), cap - 1, None), None)
        absent = {k for k in unique if kth is not None and latest.get(k, -1) < kth}
        uncertain = set(unique) - absent
        forced.append(len(absent))
        prospective_first.append(all(k not in latest for k in uncertain))
        streak = 0 if uncertain else streak + len(absent)
        if streak >= cap:
            return i, forced, prospective_first
        for k in unique:
            latest[k] = i
            latest.move_to_end(k)
    return None, forced, prospective_first


def flatten(ranks, geom):
    sites = []
    for call, tiles in enumerate(geom, 1):
        for tile, (width, _, _) in enumerate(tiles, 1):
            for layer in range(36):
                n = width if layer < 35 else int(call > 1 and tile == len(tiles))
                ids = [128 * layer + e for row in range(n) for e in ranks[call, tile, layer, row]]
                if ids:
                    sites.append(((call, tile, layer), ids))
    need(sum(len(ids) for _, ids in sites) == len(ranks) * 4, "pruning/census")
    return sites


def prices(count, seconds_num, seconds_den):
    byte_count = count * PAYLOAD
    return {
        "payload_bytes": byte_count,
        "required_B_s_ceiling": -(-byte_count * seconds_den // seconds_num),
        "gross_link_floor_ns": -(-byte_count * 10**9 // CEILING),
        "exceeds_gross_link": byte_count * seconds_den > CEILING * seconds_num,
    }


def trial(exe, sites, cap):
    solver_path = QUAL / "cache_bound.py"
    need(
        sha(solver_path) == "7a1eca13746bac6a2f0b2a989040374e801d0e058d58240d022b80ddb07b4e46",
        "solver identity",
    )
    minimum = run_path(str(solver_path))["minimum"]
    groups = [tuple(dict.fromkeys(ids)) for _, ids in sites]
    seeded = list(dict.fromkeys(k for g in groups for k in g))[:cap]
    cold, _, cold_states = replay(exe, sites, cap, [])
    warm, _, warm_states = replay(exe, sites, cap, seeded)
    conv, forced, first = certify(groups, cap)
    if conv is not None:
        need(
            cold_states[conv:] == warm_states[conv:] and cold[conv + 1 :] == warm[conv + 1 :],
            "universal state proof contradicted by constructed seed",
        )

    def summary(indices, oracle=False):
        uncertain = [i for i in indices if conv is None or i <= conv]
        exact = [i for i in indices if conv is not None and i > conv]
        ever = sum(len(groups[i]) for i in uncertain)
        upper = ever + sum(cold[i] for i in exact)
        floor = upper - (ever - sum(forced[i] for i in uncertain))
        if all(first[i] for i in uncertain):
            floor = max(floor, upper - cap)
        out = {
            "unique_lookups": sum(len(groups[i]) for i in indices),
            "cold_fills": sum(cold[i] for i in indices),
            "first_K_seed_fills": sum(warm[i] for i in indices),
            "any_start_fills": [floor, upper],
        }
        if oracle:
            opt = minimum([groups[i] for i in indices], cap)
            floor = max(floor, opt)
            out["any_start_fills"][0] = floor
            out["free_entry_optimal_replacement_floor"] = opt
        need(
            all(floor <= out[k] <= upper for k in ("cold_fills", "first_K_seed_fills")),
            "constructive state violates bounds",
        )
        out["endpoints_attained"] = sorted([out["cold_fills"], out["first_K_seed_fills"]]) == [
            floor,
            upper,
        ]
        out["any_start_hits"] = [out["unique_lookups"] - upper, out["unique_lookups"] - floor]
        out["any_start_payload_B"] = [floor * PAYLOAD, upper * PAYLOAD]
        return out

    tiles = []
    for (call, tile), items in groupby(enumerate(sites), lambda row: row[1][0][:2]):
        indices = [i for i, _ in items]
        tiles.append({"call": call, "tile": tile, **summary(indices)})
    phases = {}
    for name, lo, hi in [
        ("prefill", 1, 2),
        ("first_decode", 3, 3),
        ("decode_to_first", 3, 46),
        ("through_first_final", 1, 46),
        ("all_decode", 3, 48),
        ("all_T2", 1, 48),
    ]:
        indices = [i for i, (coord, _) in enumerate(sites) if lo <= coord[0] <= hi]
        phases[name] = summary(indices, oracle=True)
        if name in ("through_first_final", "all_decode"):
            num, den = (10, 1) if name == "through_first_final" else (47, 6)
            phases[name]["contract"] = [
                prices(n, num, den) for n in phases[name]["any_start_fills"]
            ]
    return {
        "real_slots": cap,
        "converged_after_site": None if conv is None else sites[conv][0],
        "no_repeat_among_uncertain_keys_until_convergence": all(first),
        "phases": phases,
        "tiles": tiles,
    }


def study(a):
    b = json.loads((a.build_dir / "receipt.json").read_bytes())
    exe = a.build_dir / "plan"
    need(
        sha(a.build_dir / "receipt.json") == a.build_sha256
        and b["status"] == "BUILT_IK_POLICY"
        and b["source_sha256"] == sha(HERE / "plan.cpp")
        and b["header_sha256"] == HDR
        and b["hook_sha256"] == HOOK
        and b["external_pin"] == IK["PIN"]
        and sha(Path(b["library_path"])) == b["library_sha256"] == LIB
        and b["executable_sha256"] == sha(exe),
        "unsealed policy build",
    )
    link = QUAL / "stock_link/run-01/receipt.json"
    need(
        sha(link) == "1c6c1767e044afacb3ba64e3a12241c17f1f56d04f21713a30f3ee1cadfa8f03"
        and json.loads(link.read_bytes())["gross_max_B_s"] == CEILING,
        "PCI maximum",
    )
    need(
        sha(a.inventory) == IK["INVENTORY"]
        and len(IK["layer_geometry"](a.inventory.read_bytes())) == 36
        and 3 * IK["STRIDE"] == PAYLOAD,
        "C283 authority",
    )
    ranks, geom, _, sources = PAGES["reopen"](a.p97, a.p106)
    _, _, receipt, audit = PAGES["CHAIN"]["chain"](a.p97, PAGES["P97"])
    cut = audit["http_cut"]
    need(
        (cut["sample_number"], cut["sample_call"]) == (45, 46)
        and receipt["rows"][1]["predicted_n"] == 47
        and len(geom) == 48,
        "HTTP cut/denominator",
    )
    http = a.p97 / "ON/raw/T2-request.jsonl"
    need(
        sha(http) == "d3f7cb28c8cec47d7f524876d6e1d8fce37bf73935d4fb2237946de0d14e8d96",
        "SSE identity",
    )
    frames = [json.loads(s) for s in http.read_bytes().splitlines()]
    need(
        [r["kind"] for r in frames[-2:]] == ["RESPONSE_COMPLETE", "REQUEST_TERMINAL"]
        and frames[-1]["accepted"]
        and frames[-2]["monotonic_s"] <= frames[-1]["monotonic_s"],
        "last client markers",
    )
    sites = flatten(ranks, geom)
    return {
        "status": "TRACE_DERIVED_CONDITIONAL_IK_LRU",
        "protocol_sha256": sha(HERE / "protocol.md"),
        "method_sha256": sha(Path(__file__)),
        "policy_build_sha256": a.build_sha256,
        "sources": sources
        | {"P97_HTTP": sha(http), "PCI": sha(link), "solver": sha(QUAL / "cache_bound.py")},
        "quartets": len(ranks),
        "lookup_sites": len(sites),
        "calls": len(geom),
        "first_final_sample_call": [45, 46],
        "last_output_sample_call": [47, 48],
        "client_response_complete_and_terminal_timestamped": True,
        "client_exact_last_token_compute_timestamp": None,
        "payload_B": PAYLOAD,
        "link_cap_B_s": CEILING,
        "budgets": {str(k): trial(exe, sites, k) for k in (128, 161)},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for subcmd, args in [
        ("build", ("ik", "lib")),
        ("study", ("p97", "p106", "inventory", "build-dir")),
    ]:
        child = sub.add_parser(subcmd)
        for arg in (*args, "new-output"):
            child.add_argument("--" + arg, required=True, type=Path)
        if subcmd == "study":
            child.add_argument("--build-sha256", required=True)
    a = parser.parse_args()
    a.new_output.mkdir(mode=0o700, exist_ok=False)
    try:
        result = (
            build(a.ik.resolve(), a.lib.resolve(), a.new_output)
            if a.action == "build"
            else study(a)
        )
    except Exception as exc:
        result = {"status": "FAIL_PRESERVED", "error": str(exc)}
    path = a.new_output / ".pending"
    with path.open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")
    path.rename(a.new_output / "receipt.json")
    print(result["status"])
    raise SystemExit(result["status"] == "FAIL_PRESERVED")
