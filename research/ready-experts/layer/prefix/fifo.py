"""Replay the real FIFO before the first claim of each of the two timed pairs."""

import argparse
import json
from collections import Counter, deque
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
study = run_path(HERE / "batch.py")
SRC, need, SCREEN = (study[k] for k in ("SRC", "need", "SCREEN"))


def inspect(rows, selected):
    queue, active, output, count = deque(), set(), {}, Counter()
    names = {
        tuple(key): (case, tuple(case_data["keys"][1 - i]))
        for case, case_data in selected.items()
        for i, key in enumerate(case_data["keys"])
    }
    for seq, r in enumerate(rows):
        key = SRC["key"](r)
        if r.kind == 12:
            queue.append(key)
            count["enqueue"] += 1
        elif r.kind in (13, 14):
            need(queue and queue[0] == key, "FIFO lineage")
            if r.kind == 13:
                if key in names:
                    phase, peer = names[key]
                    if phase not in output:
                        pos = queue.index(peer) if peer in queue else None
                        output[phase] = dict(
                            seq=seq,
                            first=list(key),
                            other=list(peer),
                            queue_depth=len(queue),
                            other_index=pos,
                            other_claims_active=len(active),
                            generations_already_claimed=[list(k) for k in sorted(active)],
                            head_adjacent=pos == 1,
                            intervening=[list(x) for x in list(queue)[1:pos]]
                            if pos is not None
                            else [],
                        )
                need(key not in active, "multiple worker claims")
                active.add(key)
                count["claim"] += 1
            else:
                count["skip"] += 1
            queue.popleft()
        elif r.kind == 17:
            need(key in active, "publication without claim")
            active.remove(key)
            count["publish"] += 1
        need(len(active) <= 4, "service capacity")
    need(
        not queue
        and not active
        and output.keys() == selected.keys()
        and count["claim"] == count["publish"] == 2354
        and count["enqueue"] == count["claim"] + count["skip"],
        "journal drain or population",
    )
    return dict(pairs=output, counts=count)


def run(archive):
    base = HERE / "evidence-20261128-r01/decision.json"
    report = json.loads(base.read_bytes())
    selection = report["pair"]["selection"]
    prior = SRC["pinned"](
        SCREEN["NATURAL"] / "prefill_retention/request_cost/receipt.json", SCREEN["PRIOR"]
    )
    arms = {}
    for tag in ("P97", "P106"):
        _, control = SCREEN["read_arm"](archive, tag, prior[tag])
        need(control["journal_sha256"] == report["pair"]["sources"][tag], "selection source")
        name, h, _ = SRC["SOURCES"][tag]
        root = archive / ("part-" + tag[1:]) / name
        if tag == "P97":
            rows, _ = SRC["T"]["PFJ"]["read_journal"](root / "ON/raw/events.pfj")
        else:
            _, rows, _, _ = SRC["Q"]["read_new"](root, h)
        arms[tag] = inspect(rows, selection)
        arms[tag]["journal_sha256"] = control["journal_sha256"]
    return dict(
        evidence="TRACE_DERIVED",
        arms=arms,
        parent_sha256=SRC["digest"](base),
        program_sha256=SRC["digest"](Path(__file__)),
        protocol_sha256=SRC["digest"](HERE / "fifo-protocol.md"),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        r = run(a.archive)
    except Exception as exc:
        (a.new_output_dir / "failure.json").write_text(json.dumps({"reason": repr(exc)}) + "\n")
        raise
    (a.new_output_dir / "receipt.json").write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
    print(
        {
            k: {case: v["other_index"] for case, v in arm["pairs"].items()}
            for k, arm in r["arms"].items()
        }
    )
