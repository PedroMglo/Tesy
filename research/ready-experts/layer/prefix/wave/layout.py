"""Seal a linear layout on T1 and bound its client reach on authenticated T2 journals."""

import argparse
import gzip
import json
from collections import Counter, defaultdict, deque
from itertools import combinations, groupby, pairwise
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
B = run_path(HERE.parent / "batch.py")
SRC, SCREEN, LIMIT, need = (B[name] for name in ("SRC", "SCREEN", "LIMIT", "need"))
TRAIN = run_path(HERE.parents[2] / "selection.py")
PHASES = B["PHASES"]
N, L = 128, 36


def linear_order(batches, n=N):
    """Greedy maximum-weight path forest. Zero-weight edges join its final components."""
    votes = Counter(pair for ids in batches for pair in combinations(sorted(set(ids)), 2))
    edges = sorted(combinations(range(n), 2), key=lambda p: (-votes[p], p))
    links = [[] for _ in range(n)]
    components = list(range(n))
    value = 0
    for i, j in edges:
        a, b = components[i], components[j]
        if a == b or len(links[i]) == 2 or len(links[j]) == 2:
            continue
        links[i].append(j)
        links[j].append(i)
        value += votes[i, j]
        components = [a if c == b else c for c in components]
        if len(set(components)) == 1:
            break
    ends = [e for e, neighbors in enumerate(links) if len(neighbors) == 1]
    need(len(ends) == 2, "path endpoints")
    path = [min(ends)]
    while True:
        following = [e for e in links[path[-1]] if len(path) == 1 or e != path[-2]]
        if not following:
            break
        need(len(following) == 1, "branch")
        path.append(following[0])
    need(sorted(path) == list(range(n)), "Hamiltonian path")
    return path, value


def train(arm):
    seal = SRC["pinned"](arm / "before-t2.json", TRAIN["T1_SEAL"])
    pf = TRAIN["PROFILE"]
    rows = list(pf["iter_rows"](arm / "observer/events.pfj", 0, seal["records"]))
    proof, _ = pf["prefix_grade"](rows, pf["T1"], 9)
    need(all(proof[k] == seal[k] for k in proof) and len(rows) == 87736, "unsealed prefix")
    batches = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r.kind == 11:
            batches[r.layer][r.call, r.tile].append(r.expert)
    n = sum(len(group) for layer in batches.values() for group in layer.values())
    need(n == proof["reserves"] == proof["publications"] == 5727, "T1 census")
    paths, scores = zip(*(linear_order(batches[i].values()) for i in range(L)), strict=True)
    return dict(
        status="SEALED_BEFORE_T2",
        t1_sha256=proof["sha256"],
        seal_sha256=TRAIN["T1_SEAL"],
        protocol_sha256=SRC["digest"](HERE / "layout-protocol.md"),
        source_sha256=SRC["digest"](HERE / "layout.py"),
        records=len(rows),
        reservations=n,
        order=paths,
        training_edges=scores,
    )


def queued_pairs(rows, origins):
    """Positions in the actual FIFO at the first claim, independently of the chosen layout."""
    fifo, claimed, pubs, witnessed = deque(), set(), {}, {}
    for row in rows:
        k = SRC["key"](row)
        if row.kind == 12:
            fifo.append(k)
        elif row.kind in (13, 14):
            need(fifo and fifo.popleft() == k, "FIFO order")
            if row.kind == 13:
                need(k not in claimed and k in origins, "claim identity")
                claimed.add(k)
                site = origins[k][:3]
                for pos, other in enumerate(fifo, 1):
                    if other != k and other not in claimed and origins[other][:3] == site:
                        pair = site, tuple(sorted([k[3], other[3]]))
                        witnessed.setdefault(pair, pos)
        elif row.kind == 17:
            need(k in claimed and k not in pubs, "publication identity")
            pubs[k] = row.ns
    need(not fifo and claimed == origins.keys() == pubs.keys(), "final queue")
    return witnessed, pubs


def envelope(bounds, outside):
    lo, first, last, hi = bounds
    need(0 <= lo <= first <= last <= hi and outside[0] <= lo <= hi <= outside[1], "interval")
    return lo, hi


def arm(archive, tag, prior):
    (_, first, decode), auth = SCREEN["read_arm"](archive, tag, prior)
    folder, digest, _ = SRC["SOURCES"][tag]
    root = archive / ("part-" + tag[1:]) / folder
    if tag == "P97":
        rows, _ = SRC["T"]["PFJ"]["read_journal"](root / "ON/raw/events.pfj")
    else:
        _, rows, _, _ = SRC["Q"]["read_new"](root, digest)
    waves, origins = SRC["timeline"](rows)
    witness, pubs = queued_pairs(rows, origins)
    calls = SRC["NATIVE"]["host_trace"](rows)["calls"]
    per_call = defaultdict(list)
    for w in waves:
        per_call[w.site[0]].append(w)
    regions = []
    seen = set()
    for call in calls:
        num = call["number"]
        groups = [list(ws) for _, ws in groupby(per_call[num], lambda w: w.site[:3])]
        for i, group in enumerate(groups):
            site = group[0].site[:3]
            keys = [k for w in group for k in w.reserved]
            ids = sorted(k[3] for k in keys)
            need(len(ids) == len(set(ids)) and not seen.intersection(keys), "duplicate expert")
            seen.update(keys)
            need(
                all(
                    origins[k][:3] == site and group[0].start <= pubs[k] <= group[-1].end
                    for k in keys
                ),
                "generation crossing region",
            )
            if not keys:
                continue
            lo, hi = envelope(
                (
                    groups[i - 1][-1].end if i else call["enter_ns"],
                    group[0].start,
                    group[-1].end,
                    groups[i + 1][0].start if i + 1 < len(groups) else call["return_ns"],
                ),
                (call["enter_ns"], call["return_ns"]),
            )
            witnessed = [
                [a, b, witness[site, (a, b)]]
                for a, b in combinations(ids, 2)
                if (site, (a, b)) in witness
            ]
            regions.append([*site, ids, lo, hi, witnessed])
    need(seen == origins.keys() and len(seen) == auth["jobs"] == 2354, "reservation population")
    return dict(
        journal_sha256=auth["journal_sha256"],
        manifest_sha256=auth["manifest_sha256"],
        trajectory_sha256=auth["trajectory_sha256"],
        before_ns=dict(first_final=first, decode=decode),
        outside_calls_ns=auth["outside_calls_ns"],
        regions=regions,
    )


def score(raw, order):
    need(
        len(order) == L and all(sorted(path) == list(range(N)) for path in order), "invalid layout"
    )
    ranks = [{e: pos for pos, e in enumerate(path)} for path in order]
    counts, spans = defaultdict(Counter), defaultdict(list)
    for call, _, layer, ids, lo, hi, witnessed in raw["regions"]:
        phase = SCREEN["phase"](call)
        need(len(ids) == len(set(ids)), "one generation per expert per region")
        positions = sorted(ranks[layer][e] for e in ids)
        edges = sum(b == a + 1 for a, b in pairwise(positions))
        c = counts[phase]
        c.update(generations=len(ids), eligible_groups=int(edges > 0), adjacency_edges=edges)
        if edges:
            spans[phase, call].append((lo, hi))
        witnesses = [p for a, b, p in witnessed if abs(ranks[layer][a] - ranks[layer][b]) == 1]
        need(len(witnesses) <= edges and all(p >= 1 for p in witnesses), "witness conservation")
        c.update(
            in_queue=len(witnesses),
            head=sum(p == 1 for p in witnesses),
            first_four=sum(p < 4 for p in witnesses),
        )
    output = {}
    for clock, phases in PHASES.items():
        c = sum((counts[phase] for phase in phases), Counter())
        credit = sum(
            B["reach"]["union_ns"](items) for (p, _), items in spans.items() if p in phases
        )
        row = dict(counts=dict(c), covered_ns=credit)
        if clock != "prefill":
            before = raw["before_ns"][clock]
            floor = before - credit
            need(raw["outside_calls_ns"][clock] <= floor <= before, "client conservation")
            row.update(floor_ns=floor, still_needed_ns=max(0, floor - LIMIT[clock]))
        output[clock] = row
    verdict = (
        "NO_GO_ISOLATED" if any(output[k]["still_needed_ns"] for k in LIMIT) else "HEADROOM_ONLY"
    )
    return dict(scopes=output, decision=verdict)


def evaluate(archive, plan, sha):
    selected = SRC["pinned"](plan, sha)
    need(
        selected["status"] == "SEALED_BEFORE_T2"
        and selected["source_sha256"] == SRC["digest"](HERE / "layout.py")
        and selected["protocol_sha256"] == SRC["digest"](HERE / "layout-protocol.md")
        and selected["seal_sha256"] == TRAIN["T1_SEAL"],
        "plan provenance",
    )
    prior = SRC["pinned"](
        SCREEN["NATURAL"] / "prefill_retention/request_cost/receipt.json", SCREEN["PRIOR"]
    )
    old = json.loads((HERE.parent / "evidence-20261128-r01/batch.json").read_bytes())
    arms, inputs = {}, {}
    for tag in ("P97", "P106"):
        raw = arm(archive, tag, prior[tag])
        controls = score(raw, [list(range(N))] * L)
        for clock in PHASES:
            actual = old["arms"][tag]["scopes"][clock]["counts"]
            new = controls["scopes"][clock]["counts"]
            need(
                new["adjacency_edges"] == actual["numeric_adjacent"]
                and new["generations"] == actual["generations"],
                "independent control",
            )
        arms[tag] = dict(
            **{k: v for k, v in raw.items() if k != "regions"},
            numeric=controls,
            trained=score(raw, selected["order"]),
        )
        inputs[tag] = raw["regions"]
    need([g[:4] for g in inputs["P97"]] == [g[:4] for g in inputs["P106"]], "work changed")
    return dict(evidence="TRACE_DERIVED_CONDITIONAL", plan_sha256=sha, arms=arms), inputs


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest="action", required=True)
    train_args = subs.add_parser("train")
    train_args.add_argument("--t1-arm", type=Path, required=True)
    score_args = subs.add_parser("score")
    score_args.add_argument("--archive", type=Path, required=True)
    score_args.add_argument("--plan", type=Path, required=True)
    score_args.add_argument("--plan-sha256", required=True)
    for sub in (train_args, score_args):
        sub.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    out = a.new_output_dir
    out.mkdir(mode=0o700)
    try:
        if a.action == "train":
            result = train(a.t1_arm)
        else:
            result, samples = evaluate(a.archive, a.plan, a.plan_sha256)
            compact = gzip.compress(json.dumps(samples, separators=(",", ":")).encode(), mtime=0)
            (out / "regions.json.gz").write_bytes(compact)
            result["regions_sha256"] = SRC["digest"](out / "regions.json.gz")
        pending = out / ".pending"
        pending.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        pending.rename(out / "receipt.json")
    except (ValueError, OSError, TypeError, KeyError, AssertionError) as exc:
        (out / "failure.json").write_text(
            json.dumps({"status": "FAIL_PRESERVED", "reason": repr(exc)}) + "\n"
        )
        raise
    print(SRC["digest"](out / "receipt.json"))
