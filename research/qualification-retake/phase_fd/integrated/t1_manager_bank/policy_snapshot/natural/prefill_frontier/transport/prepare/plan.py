"""Seal every disk and bank admission of the two carry-policy prefill calls."""

import argparse
import json
import os
import resource
import signal
import subprocess
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
NAT = HERE.parents[2]
PRIOR = run_path(NAT / "replay/decode_clock/transport/prepare.py")
FRONT = run_path(NAT / "prefill_frontier/screen.py")
replay, dc = PRIOR["prev"], PRIOR["dc"]
need, sha, encode = PRIOR["need"], PRIOR["sha"], PRIOR["encode"]
WIDTHS = ((5,), (32, 32, 32, 32, 20))
SOURCES = ("bank", "disk")


def sites(start):
    for ci, tiles in enumerate(WIDTHS):
        for ti, width in enumerate(tiles, 1):
            final = ci == 1 and ti == len(tiles)
            for layer in range(36 if final else 35):
                rows = 1 if layer == 35 else width
                n = min(rows * 4, 128)
                for wave in [-1] if n <= 40 else range((n + 17) // 18):
                    yield (start + ci, ti, layer, wave), rows


def record(groups, args):
    result = []
    order = iter(groups)
    start = groups[0]["site"][0]

    class Recorder(replay["Manager"]):
        def callback(self, layer, wave, ranks):
            source = next(order)
            site = source["site"]
            need(site[2:] == (layer, wave), "callback association")
            allocations, demands = super().callback(layer, wave, ranks)
            if site[0] in (start, start + 1):
                result.append((site, list(ranks), list(allocations)))
            return allocations, demands

    trajectory = dc["same_function"](replay["trajectory"], {"Manager": Recorder})
    _, ctrl = replay["trajectory"](groups, *args, priority=False, restore=False, reference=None)
    _, c = trajectory(groups, *args, priority=True, restore=False, reference=None)
    need(next(order, None) is None, "incomplete carry trajectory")
    return result, ctrl, c


def check_reservations(ranks, wave, allocations, state):
    """Independently check observed rank order, generation and victim per physical slot."""
    unique = list(dict.fromkeys(ranks))
    for i in range(0, len(ranks), 4):
        need(
            len(set(ranks[i : i + 4])) == 4 and all(0 <= e < 128 for e in ranks[i : i + 4]), "top-4"
        )
    current = unique if wave < 0 else unique[wave * 18 : (wave + 1) * 18]
    following = [] if wave < 0 else unique[(wave + 1) * 18 : (wave + 2) * 18]
    # Existing identities can be evicted while planning this wave. Test order and
    # bindings in replay order, then confirm every requested/preloaded member is present.
    choices = [(cause, e) for cause, ids in ((0, current), (2, following)) for e in ids]
    positions = {q: i for i, q in enumerate(choices)}
    order = []
    changed = set()
    for e, s, g, old, reason in allocations:
        need(
            (reason, e) in positions
            and 0 <= s < 40
            and s not in changed
            and state[s] == (old, g - 1)
            and e not in {v[0] for v in state},
            "reservation binding",
        )
        order.append(positions[reason, e])
        changed.add(s)
        state[s] = (e, g)
    need(all(a < b for a, b in zip(order, order[1:], strict=False)), "reservation order")
    need(set(current + following) <= {v[0] for v in state}, "unserved wave")


def materialize(captured, slots, bank, bases, index):
    groups = []
    state = [[(v[0], v[1]) for v in slots[k * 40 : (k + 1) * 40]] for k in range(36)]
    start = captured[0][0][0]
    for (site, ranks, allocations), (expected, nrows) in zip(captured, sites(start), strict=True):
        need(site == expected and len(ranks) == 4 * nrows, "complete tile/layer/wave geometry")
        call, tile, layer, wave = site
        check_reservations(ranks, wave, allocations, state[layer])
        jobs = []
        for ordinal, (e, s, g, old, reason) in enumerate(allocations):
            entry = index["experts"][layer * 128 + e]
            offset = (layer * 128 + e) * PRIOR["full"]["STRIDE"]
            need(
                (entry["layer"], entry["expert"], entry["pack_offset"]) == (layer, e, offset),
                "pack record",
            )
            jobs.append(
                dict(
                    ordinal=ordinal,
                    expert=e,
                    slot=s,
                    generation=g,
                    victim=old,
                    source_enqueue=reason,
                    source="bank" if e in bank[layer] else "disk",
                    pack_offset=offset,
                    pack_bytes=PRIOR["full"]["WINDOW"],
                    components=PRIOR["components"](entry, bases[layer]),
                )
            )
        groups.append(
            dict(
                call=call,
                call_tokens=(5, 148)[call - start],
                tile=tile,
                tile_tokens=WIDTHS[call - start][tile - 1],
                rows=nrows,
                layer=layer,
                wave=wave,
                tier="CPU" if layer < 25 else "CUDA0",
                ranks=ranks,
                jobs=jobs,
            )
        )
    return groups


def counts(groups, ref, bank):
    result = {ph: {tier: Counter() for tier in ("cpu", "cuda")} for ph in ("call5", "call148")}
    by_tile = {}
    disk = []
    for group in groups:
        layer = group["layer"]
        tier = "cpu" if layer < 25 else "cuda"
        need(group["tier"] == ("CPU" if layer < 25 else "CUDA0"), "physical tier")
        call = group["call_tokens"]
        key = f"call{call}"
        local = result[key][tier]
        tile = by_tile.setdefault((call, group["tile"]), Counter())
        local["callbacks"] += 1
        for j in group["jobs"]:
            source = j["source"]
            need(source == ("bank" if j["expert"] in bank[layer] else "disk"), "source binding")
            local[source + "_jobs"] += 1
            tile[source + "_jobs"] += 1
            local["preload" if j["source_enqueue"] == 2 else "demand"] += 1
            if source == "disk":
                disk.append(
                    (
                        group["call"],
                        group["tile"],
                        layer,
                        group["wave"],
                        j["ordinal"],
                        j["expert"],
                        j["slot"],
                        j["generation"],
                        j["pack_offset"],
                    )
                )
                local["gguf_pread_bytes"] += sum(c["aligned_bytes"] for c in j["components"])
                local["packed_pread_bytes"] += j["pack_bytes"]
                local["payload_bytes"] += sum(c["size_bytes"] for c in j["components"])
    for label, (n_disk, n_bank) in zip(("call5", "call148"), ((34, 25), (1024, 201)), strict=True):
        for tier, observed in result[label].items():
            gold = ref[label][tier]
            need(
                observed["bank_jobs"] == gold.get("bank_hits", 0)
                and observed["payload_bytes"] == observed["disk_jobs"] * 13219200
                and all(
                    observed[k] == gold.get(k, 0)
                    for k in ("disk_jobs", "gguf_pread_bytes", "packed_pread_bytes")
                )
                and observed["bank_jobs"] + observed["disk_jobs"] == gold["admissions"],
                "published coverage",
            )
        combined = sum(result[label].values(), Counter())
        need((combined["disk_jobs"], combined["bank_jobs"]) == (n_disk, n_bank), "call population")
    return dict(
        by_call_and_tier=result,
        by_tile={f"{a}/{b}": row for (a, b), row in by_tile.items()},
        ordered_disk_sha256=PRIOR["digest"](disk),
    )


def execute(a):
    manifest = FRONT["pinned"](a.part63 / "manifest.json", FRONT["SEALS"]["archive63"])["files"]
    family = FRONT["FAMILY_NAME"]
    relative = "tesy-policy-natural-replay-20261125-r02/receipt.json"
    for name, key in (
        (family + "/receipt.json", "family"),
        (family + "/ON/receipt.json", "arm"),
        (family + "/ON/raw/events.pfj", "journal"),
        (relative, "replay"),
    ):
        need(manifest[name]["sha256"] == FRONT["SEALS"][key], "archive linkage: " + key)
    gold = FRONT["pinned"](a.part63 / relative, FRONT["SEALS"]["replay"])
    rows, slots, words, calls, interval, bank, bases, origin = replay["sources"](
        a.part63 / family, dc["FAMILY"]
    )
    need(all(gold[k] == v for k, v in origin.items()), "sealed selector and initial snapshot")
    start = rows[0].call
    for i, w in enumerate(WIDTHS):
        need(
            [(r.tile, r.a) for r in rows if r.kind == 3 and r.call == start + i]
            == list(enumerate(w, 1)),
            "real microbatch widths",
        )
    index = PRIOR["full"]["read"](a.index, PRIOR["full"]["INDEX"])
    PRIOR["full"]["validate_placement"](PRIOR["full"]["read"](a.placement, PRIOR["PLACEMENT"]))
    PRIOR["metadata"](index, bases)
    groups, reads, workers = replay["segment"](rows)
    cap, r0, carry = record(groups, (reads, slots, words, calls, interval, bank, bases))
    need(
        workers == gold["observed"]
        and r0 == gold["r0"]
        and carry == {k: v for k, v in gold["carry"].items() if k != "comparison"},
        "complete replay",
    )
    grid = materialize(cap, slots, bank, bases, index)
    report = counts(grid, gold["carry"]["variants"]["bank"], bank)
    ids = dict(
        model_sha256=PRIOR["MODEL"],
        pack_sha256=PRIOR["full"]["PACK"],
        index_sha256=PRIOR["full"]["INDEX"],
        placement_sha256=PRIOR["PLACEMENT"],
        family_sha256=dc["FAMILY"],
        journal_sha256=origin["pfj_sha256"],
        policy_sha256=origin["policy_sha256"],
        prefix_sha256=origin["prefix_sha256"],
        causal_slot_stream_sha256=carry["inferred_slot_stream_sha256"],
    )
    plan = dict(
        schema="tesy-prefill-transport-v1", groups=grid, component_order=list(PRIOR["ROLES"]), **ids
    )
    data = encode(plan) + b"\n"
    need(len(data) < 8 << 20, "private plan output cap")
    with (a.new_output_dir / "plan.json").open("xb") as f:
        f.write(data)
    return dict(
        status="PASS_ORDERED_PREFILL_TRANSPORT_PLAN",
        plan_sha256=sha(a.new_output_dir / "plan.json"),
        plan_bytes=len(data),
        groups=len(grid),
        weights_bytes_read=0,
        model_forwards=0,
        **ids,
        **report,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("part63", "index", "placement", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        git = [
            "git",
            "--no-optional-locks",
            "-c",
            "core.preloadIndex=false",
            "-c",
            "index.threads=1",
            "-C",
            HERE,
        ]
        need(not subprocess.check_output([*git, "status", "--porcelain"]), "dirty checkout")
        resource.setrlimit(resource.RLIMIT_AS, (768 << 20, 768 << 20))
        resource.setrlimit(resource.RLIMIT_CPU, (118, 120))
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("120s")))
        signal.alarm(120)
        r = execute(a) | dict(
            commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
            program_sha256=sha(HERE / "plan.py"),
            protocol_sha256=sha(HERE / "protocol.md"),
        )
    except Exception as e:
        r = dict(status="FAIL_PRESERVED", reason=f"{type(e).__name__}: {e}")
    finally:
        signal.alarm(0)
    (a.new_output_dir / "receipt.json").write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
