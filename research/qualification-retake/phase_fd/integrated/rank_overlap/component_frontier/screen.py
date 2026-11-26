"""Reopen the packed request and bound same-generation partial FFN availability."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "packed_decode"
P = run_path(str(PREVIOUS / "screen.py"))
C, Q, T = P["C"], P["Q"], P["T"]
check, digest = C["check"], C["digest"]
METHOD = "252d1e51fb650803f899277e02967d3c82e1a8bede0bb870da8c6996abd48b80"
REFERENCE = "cb19931b91e919049635595de1abc377b88a547aa718c6ffde9e6a8ee47653b1"
PREVIOUS_SRC = "af6dc34066f955b5d11d566aad0a668318096e452b50aad878096bde21ec6e32"
MODES = ("full", "first_gate", "read", "begin")


def observations(rows, ready):
    """Times of successful whole-read and each role SET of the official generation."""
    service = defaultdict(list)
    for r in rows:
        if r.kind == 30:
            if r.c < 0:  # Completed service/retry validity is checked by the source auditor.
                continue
            check(r.c >= 3 * T["SLAB"], "short payload")
            service[T["PFJ"]["identity"](r)].append(("read", r.begin, r.ns))
        elif r.kind == 16:
            service[T["PFJ"]["identity"](r)].append((r.component, r.begin, r.ns))
    stamps = {}
    for k, pub in ready.items():
        if pub == 0:
            stamps[k] = (0, 0, 0)
            continue
        events = service.pop(k, [])
        check([e[0] for e in events] == ["read", 0, 1, 2], "missing or reordered weight role")
        last = 0
        for _, begin, end in events:
            check(last <= begin <= end <= pub, "component/whole-generation chronology")
            last = end
        stamps[k] = pub, events[1][2], events[0][2]
    check(not service, "unpublished generation")
    return stamps


def credits(w, after, stamps):
    if after:
        check(w.end <= after.begin, "overlapping chronological callbacks")
    fence = (
        after is not None
        and (w.call, w.tile) == (after.call, after.tile)
        and (w.layer == after.layer or after.nrows)
    )
    gap = after.begin - w.end if fence else None
    check(w.begin <= w.end and len(w.demand) == len(set(w.demand)), "invalid wave")
    states = [stamps[k] for k in w.demand]
    check(all(0 <= read <= gate <= pub <= w.end for pub, gate, read in states), "readiness order")
    last = max([w.begin] + [s[0] for s in states])
    starts = [max(w.begin, min((s[i] for s in states), default=w.begin)) for i in range(3)] + [
        w.begin
    ]
    gain = {
        m: min(last - s, gap) if fence else last - s for m, s in zip(MODES, starts, strict=True)
    }
    pending = bool(states) and all(s[0] > w.begin for s in states)
    check(list(gain.values()) == sorted(gain.values()), "non-nested bounds")
    check(pending or gain["full"] == gain["begin"], "increment without all ranks pending")
    return gain, pending, gap, last - w.begin


def load_t2(archive, label, proof):
    name = C["SOURCES"][label][0]
    root = archive / ("part-" + label[1:]) / name / "ON"
    if label == "P97":
        rows, header = T["PFJ"]["read_journal"](root / "raw/events.pfj")
        check(header["journal_sha256"] == proof["journal_sha256"], "P97 journal")
    else:
        source = root / "observer/events.pfj"
        check(digest(source) == proof["journal_sha256"], "P106 journal")
        cut, total = Q["PROFILE"]["metadata"](source, True)
        rows = [
            r._replace(call=r.call - 86) if r.call else r
            for r in Q["PROFILE"]["iter_rows"](source, cut, total - cut)
        ]
        check(digest(source) == proof["journal_sha256"], "journal changed during read")
    return rows


def assess(rows, prior):
    waves, ready = P["OVERLAP"]["collect"](rows, 1)
    check(len(waves) == prior["source_work"]["remaps"], "wave count")
    stamps = observations(rows, ready)
    totals = defaultdict(Counter)
    candidates = []
    for i, w in enumerate(waves):
        after = waves[i + 1] if i + 1 < len(waves) else None
        gain, pending, gap, width = credits(w, after, stamps)
        old = P["OVERLAP"]["opportunity"](w, after, ready)
        check(gain["full"] == old["progressive_upper_ns"], "changed full-rank control")
        phase = (
            "prefill5"
            if w.call == 1
            else "prefill148"
            if w.call == 2
            else ("decode_early" if w.call <= 46 else "decode_tail")
        )
        tier = (
            "CPU" if w.layer < 25 else "CUDA0"
        )  # Prior verifies actual device/log + all 108 slabs.
        counter = totals[phase, tier]
        counter.update(gain)
        counter["waves"] += 1
        counter["all_pending"] += pending
        counter["positive_extension"] += gain["begin"] > gain["full"]
        if pending:
            candidates.append(
                dict(
                    call=w.call,
                    tile=w.tile,
                    layer=w.layer,
                    wave=w.ordinal,
                    ranks_or_experts=len(w.demand),
                    fence_limit_ns=gap,
                    release_window_ns=width,
                    gains_ns=gain,
                    increment_ns=gain["begin"] - gain["full"],
                )
            )
    for (p, t), data in totals.items():
        base = prior["phase_by_tier"][p][t]
        check(
            (data["waves"], data["all_pending"], data["full"])
            == (base["waves"], base["all_pending_waves"], base["progressive_upper_ns"]),
            "phase counts",
        )
    scopes = {}
    for key, ref in prior["scopes"].items():
        span, tier = key.split("/")
        modes = {}
        for mode in MODES:
            credits_ns = [
                sum(
                    totals[p, t][mode]
                    for t in ("CPU", "CUDA0")
                    if t == "CPU" or tier == "CPU_and_CUDA"
                )
                if span != "decode" or p.startswith("decode")
                else 0
                for p in P["PHASES"]
            ]
            modes[mode] = P["clocks"](
                prior["first_final_ns"],
                prior["decode_ns"],
                credits_ns[0] + credits_ns[1],
                credits_ns[2],
                credits_ns[3],
            )
        check(modes["full"] == ref["progressive"], "control outcome/clock-cut")
        scopes[key] = modes
    return dict(
        phase_by_tier={p: {t: totals[p, t] for t in ("CPU", "CUDA0")} for p in P["PHASES"]},
        all_pending_sites=candidates,
        scopes=scopes,
        first_final_ns=prior["first_final_ns"],
        decode_ns=prior["decode_ns"],
        source_work=prior["source_work"],
        route=prior["route"],
    )


def run(archive):
    check(
        digest(HERE / "protocol.md") == METHOD and digest(PREVIOUS / "screen.py") == PREVIOUS_SRC,
        "protocol or parent version",
    )
    saved = C["pinned"](PREVIOUS / "receipt.json", REFERENCE)
    check(json.loads(json.dumps(P["run"](archive))) == saved, "source study reproduction")
    arms = {}
    for label, proof in saved["sources"].items():
        arms[label] = assess(load_t2(archive, label, proof), saved["arms"][label])
    return dict(
        status="REPRODUCED_PACK_COMPONENT_FRONTIER",
        protocol_sha256=METHOD,
        source_sha256=digest(HERE / "screen.py"),
        parent_receipt_sha256=REFERENCE,
        sources=saved["sources"],
        arms=arms,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("archive", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        report = run(a.archive)
    except Exception as exc:
        report = dict(status="FAIL_PRESERVED", reason=str(exc), error=type(exc).__name__)
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    print(report["status"], report.get("reason", ""))
    raise SystemExit(report["status"] == "FAIL_PRESERVED")
