"""Compare position-aligned output words and ordered logical expert selections."""

import argparse
import json
import math
import re
import struct
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
GPU = run_path(str(HERE.parent / "review.py"))
GRADE = GPU["GRADE"]
need, digest = GPU["need"], GPU["digest"]
CPU = "95e0697e0c9d65c16a921fff06af57ddd2b43e22d4c3be39f256afe023dd5508"
PHASES = {3: ("prefill", 0, 32), 4: ("teacher", 32, 1)}
KINDS = ("ordered_equal", "same_set_reordered", "set_changed")


def route_rows(text):
    """The client prints the whole tensor name, including any scheduler suffix."""
    rows, aliases = {}, {}
    for rec in GRADE["records"](text, "ROUTE"):
        phase, *name, word = rec
        matched = re.fullmatch(r"ffn_moe_topk-([01])( \(cont\))?", " ".join(name))
        need(matched and int(phase) in PHASES, "unexpected route identity")
        _, start, count = PHASES[int(phase)]
        values = GRADE["pids"](word)
        need(len(values) == 4 * count, "truncated route")
        target = aliases if matched[2] else rows
        for i in range(count):
            key = (start + i, int(matched[1]))
            ids = values[4 * i : 4 * i + 4]
            need(key not in target, "duplicate logical route or copy")
            need(len(set(ids)) == 4 and all(0 <= n < 8 for n in ids), "invalid expert IDs")
            target[key] = ids
    need(all(k in rows and v == rows[k] for k, v in aliases.items()), "unbound route copy")
    return rows, len(aliases)


def logit_rows(data, count):
    need(len(data) == count * 128, "truncated logits")
    rows = list(struct.iter_unpack("<32f", data))
    need(all(math.isfinite(v) for row in rows for v in row), "nonfinite logits")
    return rows


def load(mode, path, grade=None):
    stdout = (path / "stdout").read_text()
    routes, copies = route_rows(stdout)
    if grade is not None:
        actual = GRADE["check_arm"](mode, stdout, (path / "stderr").read_text(), path / "native")
        need(actual == grade, f"reopened grade {mode}")
    logits = {}
    hashes = {}
    for label, start, count in PHASES.values():
        file = path / "native" / (label + ".f32")
        if file.exists():
            need(not file.is_symlink(), "linked logits")
            hashes[label] = digest(file)
            if grade is not None:
                need(hashes[label] == grade["logits_sha256"][file.name], "logit identity")
            logits.update(enumerate(logit_rows(file.read_bytes(), count), start))
    return {
        "routes": routes,
        "logits": logits,
        "source": {
            "grade_reproduced": grade is not None,
            "logical_top4_rows": len(routes),
            "scheduler_copy_rows_checked": copies,
            "logit_rows": len(logits),
            "stdout_sha256": digest(path / "stdout"),
            "logit_sha256": hashes,
        },
    }


def top(scores):
    ids = sorted(range(len(scores)), key=lambda n: (-scores[n], n))
    a, b = ids[:2]
    return {
        "winners": [n for n in ids if scores[n] == scores[a]],
        "two_ids_by_score_then_id": [a, b],
        "two_scores": [scores[a], scores[b]],
        "margin": scores[a] - scores[b],
    }


def route_kind(left, right):
    if left == right:
        return KINDS[0]
    return KINDS[1] if set(left) == set(right) else KINDS[2]


def compare(left, right):
    groups, changed, by_site = {}, {}, {}
    for phase, start, count in PHASES.values():
        for layer in (0, 1):
            classes = {kind: [] for kind in KINDS}
            shared = Counter()
            for pos in range(start, start + count):
                key = pos, layer
                if key not in left["routes"] or key not in right["routes"]:
                    continue
                a, b = left["routes"][key], right["routes"][key]
                kind = route_kind(a, b)
                classes[kind].append(pos)
                shared[len(set(a) & set(b))] += 1
                by_site[key] = kind
                if kind != KINDS[0]:
                    changed[f"{pos}:{layer}"] = [list(a), list(b)]
            groups[f"{phase}:L{layer}"] = {
                "positions": classes,
                "shared_experts_histogram": dict(sorted(shared.items())),
            }
    special, greedy, assoc, counts = {}, {}, Counter(), {}
    for label, start, count in PHASES.values():
        counts[label] = {"different_words": 0, "words": 0}
        greedy[label] = {"same": [], "changed": [], "either_tied": []}
        for pos in range(start, start + count):
            if pos not in left["logits"] or pos not in right["logits"]:
                continue
            a, b = left["logits"][pos], right["logits"][pos]
            wa, wb = (struct.pack("<32f", *row) for row in (a, b))
            counts[label]["different_words"] += sum(
                wa[i : i + 4] != wb[i : i + 4] for i in range(0, 128, 4)
            )
            counts[label]["words"] += 32
            ta, tb = top(a), top(b)
            if len(ta["winners"]) != 1 or len(tb["winners"]) != 1:
                kind = "either_tied"
            else:
                kind = "same" if ta["winners"] == tb["winners"] else "changed"
            greedy[label][kind].append(pos)
            if kind != "same" or label == "teacher":
                special[pos] = [ta, tb]
            route_classes = [by_site.get((pos, layer), "missing") for layer in (0, 1)]
            assoc[",".join(route_classes + [kind])] += 1
    return {
        "compared_top4_rows_of_66": len(by_site),
        "route_groups": groups,
        "different_quartets_by_position_layer": changed,
        "word_counts": counts,
        "strict_greedy_positions": greedy,
        "top_two_on_changed_tied_and_teacher": special,
        "joint_L0_L1_greedy_counts": dict(sorted(assoc.items())),
    }


def analyse(cpu_dir, family, family_sha):
    cpu = GPU["bound"](cpu_dir / "receipt.json", CPU)
    f = GPU["bound"](family / "receipt.json", family_sha)
    need(cpu["status"] == "PASS_TINY_HYBRID_CPU_REFERENCE", "CPU unavailable")
    need(f["status"] in (GPU["PASS"], "FAIL_PRESERVED"), "terminal required")
    GPU["identity_tree"](family, f)
    need(f["cpu_sha256"] == CPU and f["model_sha256"] == cpu["model_sha256"], "CPU linkage")
    for channel in ("stdout", "stderr"):
        need(digest(cpu_dir / channel) == cpu[channel + "_sha256"], "CPU text identity")
    arms = {"CPU": load("CPU", cpu_dir, cpu["grade"])}
    statuses = {"CPU": "COMPLETE"}
    for mode in GPU["MODES"]:
        arm = f["arms"].get(mode)
        if not arm or not arm.get("starts"):
            statuses[mode] = "NOT_RUN"
            continue
        if not (family / mode / "stdout").exists():
            statuses[mode] = "NO_STDOUT"
            continue
        arms[mode] = load(mode, family / mode, arm.get("grade"))
        statuses[mode] = "COMPLETE" if arm.get("grade") is not None else "PARTIAL"
    pairs = [("CPU", "RESIDENT"), ("RESIDENT", "BANK9"), ("RESIDENT", "BANK7")]
    return dict(
        family_status=f["status"],
        family_sha256=family_sha,
        cpu_sha256=CPU,
        status=statuses,
        evidence={m: a["source"] for m, a in arms.items()},
        pairs={
            f"{left}-{right}": compare(arms[left], arms[right])
            for left, right in pairs
            if left in arms and right in arms
        },
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cpu", type=Path, required=True)
    p.add_argument("--family", type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(exist_ok=False)
    result = analyse(a.cpu, a.family, a.family_sha256)
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )


if __name__ == "__main__":
    main()
