"""Budget the prefill on the same nominal trajectory as the physical decode service."""

import argparse
import hashlib
import json
import os
import resource
import signal
import subprocess
from collections import Counter
from fractions import Fraction
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
NATURAL = HERE.parent
INTEGRATED = NATURAL.parents[2]
NS = 10**9
BANDWIDTH = 4_500_000_000
PAYLOAD = 13_219_200
FAMILY_NAME = "tesy-policy-natural-physical-20261125-r02"
REVIEW_NAME = "tesy-decode-service-review-20261125-r02/receipt.json"
SEALS = {
    "archive63": "f46876468215957504f27d593081142a99d46220cf9ab42782965833eab1da7f",
    "archive66": "de926e27af098ac21015917772c36f5357496c3e1604b121b371e1ec5e2979e7",
    "family": "cb70c934dbbe0f1ca7452904718589b44fa906179208e7f95b0c934808d70a42",
    "arm": "8428c5ee301281ddeb1a7b1e2ed6883073e53578027139a67c2daef5b4eaaaf5",
    "journal": "5b4d1cb6827d518a72d418f0625c8ea3a6c90a2ac57ef46b9360e9a45613f311",
    "pair": "bb6e2b508bf35af6001ccbb5bec655ae3235bf69d1a8d74af84b4382b640b889",
    "cost": "19e326bc467aa5c6403a29cb3fc05357706f7d23f33bf598928352b02b00592e",
    "replay": "494bb5d2e73b4e129b020118e1bcf2110f253b1c2b565b5d110023129516aa54",
    "service": "27832256db8ae629ece5c8d95f1ce5e0d285c24cfddf3b7e110b92154ad4cbc1",
}
PROGRAMS = {
    "pipeline": (
        INTEGRATED / "tile_pipeline/screen.py",
        "94c84772be343acffd4c02a566e40a1772df147cb56a1e80e2764caf0ce7f10a",
    ),
    "census": (
        INTEGRATED / "tile_boundary_floor/gaps/screen.py",
        "f1343fc84f4a8b5b35a19c9b5470fd4ca3f6bc74e6776c164449a1f6a4641652",
    ),
    "replay": (
        NATURAL / "replay/screen.py",
        "c60861939a385fa6ff85d38840ca5255ea64bce4fbca45d195fe876de07ddd51",
    ),
    "budgets": (
        NATURAL / "pair.py",
        "e53a1000b9fe86d0932109cda4ce6da87ec0ac660c07ac38d7060c79d38aca70",
    ),
    "cost": (
        NATURAL / "cost.py",
        "01f57bac3b1e6b1839bf153002650f6b052d7aba788416399aace27a76d85287",
    ),
}


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pinned(path, expected):
    check(not path.is_symlink() and digest(path) == expected, "identity of " + path.name)
    return json.loads(path.read_bytes())


def population(phases):
    counts = {}
    for name in ("call5", "call148", "prefill", "restore", "decode"):
        row = phases[name]["all"]
        n, hits, loads = (row.get(k, 0) for k in ("admissions", "bank_hits", "disk_jobs"))
        check(n == hits + loads and min(n, hits, loads) >= 0, name + " accounting")
        check(row.get("primary_bytes", 0) == n * PAYLOAD, name + " primary")
        check(row.get("packed_pread_bytes", 0) == loads * 13_221_888, name + " padded FD")
        counts[name] = dict(
            admissions=n, bank_hits=hits, disk_jobs=loads, payload_bytes=loads * PAYLOAD
        )
    a, b, p = (counts[k] for k in ("call5", "call148", "prefill"))
    check(all(a[k] + b[k] == p[k] for k in p), "prefill bridge")
    check(
        p["disk_jobs"] == 1058
        and counts["decode"]["disk_jobs"] == 797
        and counts["restore"]["admissions"] == 0,
        "selected trajectory",
    )
    return counts


def frontier(volume, budget, gap, protected, bps=BANDWIDTH):
    """budget and gaps in ns. All boundary decisions use exact rational arithmetic."""
    check(volume > 0 and bps > 0 and 0 <= protected <= gap, "frontier geometry")
    media = Fraction(volume * NS, bps)
    max_gap = budget - media

    def min_bandwidth(g):
        return float(Fraction(volume * NS, budget - g)) if budget > g else None

    return dict(
        prefill_budget_ns=float(budget),
        payload_at_fixed_bandwidth_ns=float(media),
        max_gap_at_fixed_bandwidth_ns=float(max_gap),
        minimum_useful_Bps_serial=min_bandwidth(gap),
        minimum_useful_Bps_optimistic_pipeline=min_bandwidth(protected),
        minimum_useful_Bps_no_gaps=min_bandwidth(0),
        maximum_gap_fraction=float(max_gap / gap) if gap else None,
        serial_margin_ns=float(max_gap - gap),
        optimistic_pipeline_margin_ns=float(max_gap - protected),
        decision="NO_GO_SCHEDULE_ALONE_AT_FIXED_PRICES"
        if max_gap < protected
        else "HEADROOM_ONLY_IN_RELAXATION",
    )


def calculate(p63, p66):
    for p, h in PROGRAMS.values():
        check(digest(p) == h, "method identity " + str(p.name))
    pipeline, replay_src, budgets, cost_src = (
        run_path(str(PROGRAMS[k][0])) for k in ("pipeline", "replay", "budgets", "cost")
    )
    m63 = pinned(p63 / "manifest.json", SEALS["archive63"])["files"]
    m66 = pinned(p66 / "manifest.json", SEALS["archive66"])["files"]
    for name, key in (
        (FAMILY_NAME + "/receipt.json", "family"),
        (FAMILY_NAME + "/ON/receipt.json", "arm"),
        (FAMILY_NAME + "/ON/raw/events.pfj", "journal"),
    ):
        check(m63[name]["sha256"] == SEALS[key], "archive63 linkage")
    check(m66[REVIEW_NAME]["sha256"] == SEALS["service"], "archive66 linkage")
    service = pinned(p66 / REVIEW_NAME, SEALS["service"])
    facts = {}
    for key, stem in (("pair", "account"), ("replay", "replay"), ("cost", "cost")):
        name = f"tesy-policy-natural-{stem}-20261125-r02/receipt.json"
        check(m63[name]["sha256"] == SEALS[key], key + " archive")
        facts[key] = pinned(p63 / name, SEALS[key])
    pair, replay, cost = (facts[k] for k in ("pair", "replay", "cost"))
    on = pair["arms"]["ON"]
    check(cost_src["calculate"](pair, replay) == cost["cases"], "published costs")
    rows, *_, origins = replay_src["sources"](p63 / FAMILY_NAME, SEALS["family"])
    check(all(replay[k] == v for k, v in origins.items()), "replay origin")
    check(
        on["journal_sha256"] == SEALS["journal"] and on["receipt_sha256"] == SEALS["arm"],
        "natural process",
    )
    check(service["status"] == "REPRODUCED_FOUR_TRANSPORT_ARMS", "service review")
    work = population(replay["carry"]["variants"]["bank"])
    volume = work["prefill"]["payload_bytes"]
    start = rows[0].call
    widths = [[r.a for r in rows if r.kind == 3 and r.call == c] for c in (start, start + 1)]
    check(widths == [[5], [32, 32, 32, 32, 20]], "prefill tiles")
    tiles, tiers = pipeline["old"]["census"](rows, start)
    total = sum(tiles.values(), Counter())
    check(
        dict(total) == on["prefill_gaps"] and dict(tiers) == on["prefill_gaps_ns_by_previous_tier"],
        "own idle intervals",
    )
    original = dict(tiles={f"call{c}_tile{t}": dict(v) for (c, t), v in tiles.items()}, total=total)
    gaps = pipeline["eligible_gaps"](rows, start, original)
    host = pipeline["host_bounds"](rows, start + 1)
    turn = on["turns"][1]
    check(
        (turn["cache_n"], turn["prompt_n"], turn["predicted_n"]) == (2044, 153, 47), "client counts"
    )
    deadlines = budgets["phase_budget"](turn)
    check({str(k): v for k, v in deadlines.items()} == on["deadlines_prefill_ns"], "client clocks")
    spans = {v + k * NS // 6 for k, v in deadlines.items()}
    check(len(spans) == 1, "common span")
    span = spans.pop()
    g, protected = gaps["total_ns"], gaps["protected_ns"]
    output = {}
    for order in ("RP", "PR"):
        physical = service["arms"][order]["P"]
        clock = physical["conditional"]["common_set_floor"]
        d = clock["total_ns"]
        check(
            d - clock["inside_ns"] == 2_318_241_276
            and physical["all"]["disk_jobs"] == 797
            and physical["all"]["bank_jobs"] == 399,
            "same service population",
        )
        f = frontier(volume, span - d, g, protected)
        check(
            abs(f["serial_margin_ns"] - clock["margin_ns"]["joint"]) <= 1, "previous joint frontier"
        )
        output[order] = dict(
            conditional_decode_ns=d, tokens47_per_s=47 * NS / d, evals46_per_s=46 * NS / d, **f
        )
    return dict(
        status="REPRODUCED_SAME_T2_PREFILL_FRONTIER",
        origins=SEALS,
        work=work,
        fixed_useful_Bps=BANDWIDTH,
        useful_bytes_per_disk_job=PAYLOAD,
        budget_prefill_plus_decode_ns=span,
        six_per_s_reference={
            str(n): frontier(volume, span - Fraction(n * NS, 6), g, protected) for n in (47, 46)
        },
        pack_orders=output,
        gaps=gaps,
        prefill_tokens_by_tile=widths,
        host_bounds_r0=host,
        model_forwards=0,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("part63", "part66", "new-output-dir"):
        parser.add_argument("--" + name, required=True, type=Path)
    a = parser.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    try:
        resource.setrlimit(resource.RLIMIT_AS, (512 << 20, 512 << 20))
        signal.alarm(120)
        git = ["git", "-C", str(HERE), "-c", "core.preloadIndex=false", "-c", "index.threads=1"]
        check(not subprocess.check_output([*git, "status", "--porcelain"]), "dirty checkout")
        result = calculate(a.part63, a.part66)
        result.update(
            commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
            program_sha256=digest(Path(__file__)),
            protocol_sha256=digest(HERE / "protocol.md"),
            helper_sha256={k: h for k, (_, h) in PROGRAMS.items()},
        )
    except Exception as e:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(e).__name__}: {e}")
    target = a.new_output_dir / "receipt.json"
    with target.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
