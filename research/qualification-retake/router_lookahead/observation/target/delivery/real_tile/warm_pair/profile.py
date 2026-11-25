"""Grade the two warm C292 CPU layers and supervise the exact and timing pairs."""

import re
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
COLD = HERE.parent
BASE = run_path(str(COLD / "profile.py"))
ROOT = BASE["ROOT"]
need = BASE["need"]
WINDOW = BASE["WINDOW"]
SLAB = 4406400
OFFERS = [6, 13, 20, 21]
FALSE = {6, 13, 21}
PREP = COLD / "next_pair/later_tiles"


def key(row):
    return row["layer"], row["expert"]


def check_preparation(prep, sources):
    need(
        prep["status"] == "PASS_REAL_TILE_WARM_INPUT"
        and prep["offers"] == OFFERS
        and prep["program_sha256"] == sources["prepare_warm.py"]
        and prep["protocol_sha256"] == sources["prepare.md"],
        "unqualified warm preparation",
    )
    jobs, warm, offers = prep["entries"], prep["warm_records"], prep["offer_records"]
    need(
        Counter(r["layer"] for r in jobs) == {0: 28, 1: 4}
        and len({key(r) for r in jobs}) == 32
        and len(warm) == 80
        and [(r["layer"], r["slot"]) for r in warm]
        == [(layer, slot) for layer in (0, 1) for slot in range(40)]
        and len({key(r) for r in warm}) == 80,
        "wrong entry footprint",
    )
    need(
        [key(r) for r in offers] == [(1, expert) for expert in OFFERS]
        and {key(r) for r in prep["false_records"]} == {(1, expert) for expert in FALSE}
        and {(1, expert) for expert in FALSE}.isdisjoint(
            {key(r) for r in jobs} | {key(r) for r in warm}
        )
        and (1, 20) in {key(r) for r in jobs},
        "changed false or useful offers",
    )
    for r in jobs + warm + offers:
        need(
            r["pack_offset"] == (r["layer"] * 128 + r["expert"]) * 13258752
            and len(r["hashes"]) == 3
            and all(re.fullmatch(r"[0-9a-f]{64}", d) for d in r["hashes"]),
            "unbound pack descriptor",
        )
    for field, n in (("initial_policy", 140), ("terminal_policy", 142)):
        cut = prep[field]
        need(
            cut["manager_calls"] == n
            and cut["hot_decay_interval"] == 2304
            and cut["fifo"] == cut["claims"] == cut["loading"] == []
            and cut["productive_workers"] == [0, 1, 2, 3],
            "warm manager cut",
        )
    need(
        [prep["initial_policy"]["pools"][str(layer)]["use_counter"] for layer in (0, 1)]
        == [649, 604],
        "warm replacement clock",
    )


def authority(args, svc, prior, result):
    build = prior.sealed_json(args.build_dir / "receipt.json", args.build_sha256)
    sources = {
        "profile.py": HERE / "profile.py",
        "cold_profile.py": COLD / "profile.py",
        "protocol.md": HERE / "protocol.md",
        "prepare_warm.py": PREP / "prepare_warm.py",
        "prepare.md": PREP / "prepare.md",
    }
    repo_sources = build["repo_sources"]
    required = {HERE / "build.py", COLD / "build.py", COLD / "native.cpp", COLD / "graph.inc"}
    need(required <= {ROOT / n for n in repo_sources}, "incomplete build inputs")
    for name, digest in repo_sources.items():
        local = ROOT / name
        need(
            not Path(name).is_absolute()
            and ".." not in Path(name).parts
            and local.resolve(strict=True).is_relative_to(ROOT)
            and svc.frozen(ROOT, local, build["commit"]) == digest
            and svc.frozen(ROOT, local, args.expect_head) == digest,
            "unfrozen build source",
        )
    result["build_repo_sources"] = repo_sources
    return BASE["authorities"](
        args,
        svc,
        prior,
        result,
        sources,
        (),
        "warm-tile",
        "PASS_WARM_TILE_BUILD",
        check_preparation,
    )


def check_restore(rec):
    need(
        rec["preads"] == 80
        and rec["pread_bytes"] == 80 * WINDOW
        and rec["sets"] == 240
        and rec["set_bytes"] == 240 * SLAB
        and rec["slab_hashes"] == rec["postset_checks"] == 240
        and rec["worker_acks"] == 4
        and rec["elapsed_ns"] > 0
        and rec["initial_policy_verified"] is True
        and rec["terminal_policy_verified"] is True,
        "incomplete physical restore or terminal state",
    )
    records = rec["records"]
    need(
        len(records) == 80
        and len({(layer, slot) for layer, _, slot, *_ in records}) == 80
        and all(
            layer in (0, 1) and 0 <= expert < 128 and 0 <= slot < 40 and gen > 0 and 0 < a <= b
            for layer, expert, slot, gen, a, b in records
        ),
        "restored bindings",
    )
    target = {
        (layer, expert, slot, gen, component)
        for layer, expert, slot, gen, *_ in records
        for component in (0, 1, 2)
    }
    sets = rec["set_intervals"]
    need(
        len(sets) == 240
        and {tuple(row[:5]) for row in sets} == target
        and all(len(row) == 7 and 0 < row[5] <= row[6] for row in sets),
        "restored component coverage",
    )


def check_row(row, grade, mode, prep=None):
    need(
        row["status"] == "PASS_WARM_TILE"
        and row["grade"] == grade
        and row["mode"] == mode
        and row["offers"] == OFFERS
        and row["workers"] == 4
        and row["drained"] is True,
        "native grade, offer, or workers",
    )
    check_restore(row["restore"])
    if prep is not None:
        measured = {tuple(record[:4]) for record in row["restore"]["records"]}
        planned = {
            tuple(rec[k] for k in ("layer", "expert", "slot", "gen"))
            for rec in prep["warm_records"]
        }
        need(measured == planned, "restored slot or generation different from C292")
    bindings = row["slot_bindings"]
    official = {tuple(b[:2]) for b in bindings}
    need(
        len(official) == len(bindings) == 32
        and sum(layer == 0 for layer, expert in official) == 28
        and (1, 20) in official
        and all((1, expert) not in official for expert in FALSE),
        "official jobs",
    )
    reads = row["reads"]
    jobs = row["read_jobs"]
    need(
        32 <= jobs <= 36
        and len(reads) == jobs
        and row["pread_bytes"] == jobs * WINDOW
        and row["slab_hashes"] == (3 * jobs if grade == "EXACT" else 0),
        "physical read conservation",
    )
    ordinary, predicted = [], []
    for layer, expert, spec, begin, end in reads:
        need(layer in (0, 1) and spec in (0, 1) and 0 < begin <= end, "bad read interval")
        dest = predicted if spec else ordinary
        dest.append((layer, expert))
    need(
        len(set(ordinary)) == len(ordinary)
        and set(ordinary) <= official
        and len(set(predicted)) == len(predicted)
        and set(predicted) <= {(1, expert) for expert in OFFERS}
        and official <= set(ordinary + predicted),
        "unexpected or missing read",
    )
    if mode == "OFF":
        need(not predicted and set(ordinary) == official, "OFF speculated")
    stage = row["stage"]
    need(
        stage["reads"] == len(predicted)
        and len(ordinary) + stage["consumed"] == 32
        and 0 <= stage["consumed"] <= 1
        and (stage["consumed"] == 0 or (1, 20) in predicted),
        "ticket consumption",
    )
    service = row["service"]
    target = {(*b, component) for b in bindings for component in (0, 1, 2)}
    need(
        row["sets"] == len(service) == 96
        and {tuple(slot[:5]) for slot in service} == target
        and all(len(slot) == 7 and 0 < slot[5] <= slot[6] for slot in service),
        "authoritative SET coverage",
    )
    epochs = row["epochs_ns"]
    need(
        len(epochs) == 8
        and epochs == sorted(epochs)
        and row["elapsed_ns"] == epochs[-1] - epochs[0] > 0
        and row["drain_ns"] == epochs[-1] - epochs[5],
        "closed service clock",
    )
    return row["numeric"], bindings


if __name__ == "__main__":
    raise SystemExit(
        BASE["main"](BASE["arguments"](), authority, check_row, (3, 3), "PASS_WARM_TILE_FAMILY")
    )
