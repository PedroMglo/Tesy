"""Replay the observed natural pair, its complete selective policy state and causal bank seal."""

import argparse
import json
import os
import resource
import signal
import subprocess
import sys
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
INT = HERE.parents[3]
sys.path.insert(0, str(HERE))
from manager import Manager, OrderUnknown, charge, repair, require, totals  # noqa: E402

policy_format = run_path(HERE.parents[1] / "review.py")
audit = run_path(INT / "t1_capture/audit.py")
fd = audit["fd"]
sha = policy_format["sha"]
BUDGET = (10690306614, 11440306616)


def pinned(root, name, digest, cap):
    p = root / name
    require(
        not p.is_symlink() and 0 < p.stat().st_size <= cap and sha(p) == digest, "seal: " + name
    )
    return p


def sources(family, digest):
    small = 2 << 20
    result = json.loads(pinned(family, "receipt.json", digest, small).read_bytes())
    require(
        result["status"] == "PASS_C281_NATURAL_POLICY_PAIR",
        "qualified complete natural pair required",
    )
    for mode in ("OFF", "ON"):
        armhash = result["arms"][mode]["receipt_sha256"]
        arm = json.loads(pinned(family / mode, "receipt.json", armhash, small).read_bytes())
    root = family / "ON"
    sealed = json.loads(pinned(root, "before-t2.json", arm["before_t2_sha256"], small).read_bytes())
    p_sel = pinned(root, "before-t2-candidates.json", sealed["candidate_file_sha256"], small)
    require(sha(p_sel) == arm["t1_candidates_sha256"], "T1 selection receipt linkage")
    journal = pinned(root, "raw/events.pfj", arm["journal_sha256"], 32 << 20)
    rows, header = fd.read_journal(journal)
    count = sealed["records"]
    require(
        count == arm["prefix_records"] and 0 < count < len(rows) and sealed["bytes"] == count * 96,
        "T1 byte seal",
    )
    prefix = rows[:count]
    require(audit["record_digest"](prefix) == sealed["sha256"], "T1 pre-POST prefix bytes")
    selection = audit["capture_prefix"](prefix)
    require(
        json.loads(json.dumps(selection)) == json.loads(p_sel.read_bytes()),
        "sealed T1 selection vs prefix",
    )
    table = selection["capacities"]["353"]
    keys = table["ordered_keys"]
    require(table["identified"] and len(set(map(tuple, keys))) == len(keys) == 353, "T1 washout")
    slots, fifo, _ = audit["state_before"](prefix)
    require(not fifo and all(x[2] != 1 and x[3] == 0 for x in slots), "pending T1 at T2")
    h, words = policy_format["parse_policy"](
        pinned(root, "raw/policy.bin", arm["policy_sha256"], 48800).read_bytes()
    )
    start = rows[count]
    require(
        len(words) == 36
        and arm["policy_bytes"] == 48800
        and h[:6] == (1, 1, start.call, 5, 2044, 2048)
        and h[7:] == (2304, 4, 36, 40, 128, 0, 0, 0)
        and start.kind == 1
        and (start.a, start.b, start.c) == (5, 2044, 2048)
        and start.call == selection["t1_calls"] + 1,
        "sidecar does not authenticate the first T2 ENTER",
    )
    geometry = [(r.a, r.b, r.c) for r in rows[count:] if r.kind == 1]
    require(
        geometry == [(5, 2044, 2048), (148, 2049, 2196)] + [(1, p, p) for p in range(2197, 2243)],
        "two prefill calls and 46 decode steps",
    )
    conserved = audit["conservation"](rows, header, None, start.call)
    require(conserved["status"] == "PASS", "PFJ1 conservation")
    bases = [[None] * 3 for _ in range(36)]
    for r in prefix:
        if r.kind == 8:
            require(r.b == 4406400 and bases[r.layer][r.component] is None, "three weight regions")
            bases[r.layer][r.component] = (r.a, r.b)
    require(all(all(x is not None for x in rr) for rr in bases), "108 GGUF weight regions")
    banks = [set() for _ in range(36)]
    for layer, e in keys:
        banks[layer].add(e)
    costs = {k: v for k, v in table.items() if k != "ordered_keys"}
    return (
        rows[count:],
        slots,
        words,
        h[6],
        h[7],
        banks,
        bases,
        dict(
            family_receipt_sha256=digest,
            on_receipt_sha256=armhash,
            pfj_sha256=header["journal_sha256"],
            policy_sha256=arm["policy_sha256"],
            prefix_sha256=sealed["sha256"],
            t1_candidates_sha256=sha(p_sel),
            t1_prefix=costs,
            bank_capacity_bytes=353 * 13219200,
            t1_victim_offers=selection["victim_offers"],
            t1_distinct_victims=selection["distinct_victim_keys"],
        ),
    )


def segment(rows):
    groups = []
    reads = Counter()
    worker = Counter()
    owner = {}
    published = set()
    promoted = []
    for r in rows:
        kind = fd.NAMES[r.kind]
        key = (r.layer, r.slot, r.gen, r.expert)
        if kind == "REMAP_BEGIN":
            site = (r.call, r.tile, r.layer, r.wave)
            group = dict(site=site, rows=r.a, ranks=[], new=[], demands=[])
            groups.append(group)
        elif kind == "RANKS":
            group["ranks"].extend((r.a >> (8 * k)) & 255 for k in range(4))
        elif kind == "RESERVE":
            require(key not in owner, "duplicate RESERVE")
            owner[key] = r
            group["new"].append((r.expert, r.slot, r.gen, r.a))
        elif kind == "ENQUEUE" and r.a != 1:
            added = group["new"][-1]
            require(
                len(added) == 4 and added[:3] == (r.expert, r.slot, r.gen) and r.a in (0, 2),
                "origin ENQUEUE",
            )
            group["new"][-1] = (*added, r.a)
        elif kind == "ENQUEUE":
            require(key in owner and key not in published, "promotion must precede publication")
            promoted.append((group, key))
        elif kind == "DEMAND":
            group["demands"].append((r.expert, r.slot, r.gen))
        elif kind == "PUBLISH":
            published.add(key)
        elif kind == "READ":
            require(
                r.b == r.c, "partial aligned transfer; real counts require explicit EOF pricing"
            )
            reads[(r.call, r.layer < 25)] += r.c
        if kind in (
            "DISPATCH",
            "SKIP",
            "SET",
            "READ",
            "PUBLISH",
            "RESERVE",
            "VICTIM_WAIT",
            "CANCEL_QUEUED",
        ):
            worker[kind] += 1
    require(
        len(owner) == len(published) == worker["RESERVE"] == worker["PUBLISH"] == worker["DISPATCH"]
        and set(owner) == published
        and worker["SET"] == worker["READ"] == 3 * len(owner)
        and not worker["CANCEL_QUEUED"]
        and not worker["VICTIM_WAIT"],
        "reservation/READ/SET conservation",
    )
    require(len(promoted) == worker["SKIP"], "duplicate promotions vs FIFO skips")
    for group, key in promoted:
        require((key[3], key[1], key[2]) in group["demands"], "promoted work is not this demand")
    return groups, reads, dict(worker)


def by_tier():
    return {"cpu": Counter(), "cuda": Counter()}


def clone(manager, bank):
    states = []
    words = []
    for p in manager.pools:
        require(
            not p.possible_loading and p.next_wave == p.next_count, "decode cut pending/partial"
        )
        states.extend((e, g, 0 if e == -1 else 2, 0) for e, g in zip(p.ids, p.gen, strict=True))
        words.append((p.clock, *p.ages, *p.heat))
    return Manager(states, words, manager.calls, manager.interval, bank)


def trajectory(
    groups, reads, slots, words, calls, interval, bank, bases, *, priority, restore, reference
):
    empty = [set() for _ in range(36)]
    selector = bank if priority else empty
    m = Manager(slots, words, calls, interval, selector)
    sources_by_arm = {
        name: {phase: by_tier() for phase in ("prefill", "call5", "call148", "decode", "restore")}
        for name in ("disk", "bank")
    }
    refcut = None
    detail = {}
    cut = groups[0]["site"][0] + 2
    ranks = None
    actual_sum = Counter()
    checked = 0
    for group in groups:
        call, tile, layer, w = group["site"]
        if call == cut and refcut is None:
            refcut = clone(m, selector)
            if restore:
                for name, source in (("disk", empty), ("bank", bank)):
                    detail = repair(m, reference, source, bases, sources_by_arm[name]["restore"])
                rebuilt = clone(reference, selector)
                rebuilt.proofs, rebuilt.emitted = m.proofs, m.emitted
                m = rebuilt
        if w in (-1, 0):
            ranks = group["ranks"]
        else:
            require(not group["ranks"], "duplicate rank vector in continuation wave")
        require(4 * group["rows"] == len(ranks), "missing ranked tokens")
        new, demands = m.callback(layer, w, ranks)
        if not priority:
            require(
                new == group["new"] and demands == group["demands"],
                "R0 decision mismatch at " + str(group["site"]),
            )
            checked += 1
        phase = "prefill" if call < cut else "decode"
        for expert, *_ in new:
            for name, source in (("disk", empty), ("bank", bank)):
                ledger = sources_by_arm[name][phase]
                before = ledger["cpu" if layer < 25 else "cuda"]["gguf_pread_bytes"]
                charge(ledger, layer, expert, source, bases)
                if call < cut:
                    portion = "call5" if call == cut - 2 else "call148"
                    charge(sources_by_arm[name][portion], layer, expert, source, bases)
                if name == "disk" and not priority:
                    actual_sum[call, layer < 25] += (
                        ledger["cpu" if layer < 25 else "cuda"]["gguf_pread_bytes"] - before
                    )
    require(refcut is not None, "missing prefill/decode cut")
    require(
        all(not p.possible_loading and p.next_wave == p.next_count for p in m.pools),
        "final pending loads/waves",
    )
    if not priority:
        require(actual_sum == reads, "R0 requested/returned bytes by call and device")
    out = {
        name: {phase: totals(c) for phase, c in phases.items()}
        for name, phases in sources_by_arm.items()
    }
    return refcut, dict(
        variants=out,
        r0_sites_checked=checked,
        repair=detail,
        induction=dict(m.proofs),
        inferred_slot_stream_sha256=m.emitted.hexdigest(),
    )


def compare(base, alt):
    results = {}
    for kind in ("disk", "bank"):
        b, a = base["variants"][kind], alt["variants"][kind]

        def counts(arm, phase):
            return arm[phase]["all"].get("disk_jobs", 0)

        saved = {ph: counts(b, ph) - counts(a, ph) for ph in ("prefill", "decode")}
        saved["prefill_including_restore"] = saved["prefill"] - counts(a, "restore")
        payload = (counts(a, "prefill") + counts(a, "restore")) * 13219200
        results[kind] = dict(
            disk_jobs_saved=saved,
            conditional_payload_margins_bytes={str(budget): budget - payload for budget in BUDGET},
            decision="GO_COUNTS_FIXTURE_ONLY"
            if min(saved["decode"], saved["prefill_including_restore"]) > 0
            else "NO_GO_SIMULTANEOUS_COUNT_REDUCTION",
        )
    return results


def execute(a):
    rows, slots, words, calls, interval, bank, bases, out = sources(a.family, a.family_sha256)
    groups, reads, out["observed"] = segment(rows)
    args = (groups, reads, slots, words, calls, interval, bank, bases)
    ref, r0 = trajectory(*args, priority=False, restore=False, reference=None)
    out["r0"] = r0
    for label, rest in (("carry", False), ("restored", True)):
        try:
            _, alt = trajectory(*args, priority=True, restore=rest, reference=ref)
            alt["comparison"] = compare(r0, alt)
            out[label] = alt
        except OrderUnknown as exc:
            out[label] = {"decision": "INCONCLUSIVE_SERVICE_ORDER", "reason": str(exc)}
    return out | {"status": "PASS_OBSERVED_R0_AND_CAUSAL_SCREEN"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family", type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(exist_ok=False)
    out = {"status": "FAIL_PRESERVED"}
    try:
        repo = HERE.parents[7]
        git = [
            "git",
            "--no-optional-locks",
            "-c",
            "core.preloadIndex=false",
            "-c",
            "index.threads=1",
            "-C",
            repo,
        ]
        require(
            not subprocess.check_output([*git, "status", "--porcelain"], timeout=10),
            "dirty repository",
        )
        rev = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True, timeout=10).strip()
        resource.setrlimit(resource.RLIMIT_AS, (768 << 20, 768 << 20))
        resource.setrlimit(resource.RLIMIT_CPU, (118, 120))
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("wall limit")))
        signal.alarm(120)
        out = execute(a) | {"measurement_commit": rev, "protocol_sha256": sha(HERE / "protocol.md")}
    except (
        KeyError,
        ValueError,
        TypeError,
        IndexError,
        MemoryError,
        OSError,
        TimeoutError,
        OrderUnknown,
    ) as exc:
        out.update(error=f"{type(exc).__name__}: {exc}")
    finally:
        signal.alarm(0)
    (a.new_output_dir / "receipt.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(out["status"], out.get("error", ""))
    return int(out["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    sys.exit(main())
