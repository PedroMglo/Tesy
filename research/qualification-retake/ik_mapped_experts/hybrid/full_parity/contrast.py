"""Independent contrasts for already authenticated private logits and bank service ledgers."""

import json
import math
import struct
from itertools import zip_longest
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
CPU = run_path(str(HERE.parents[1] / "cpu_numeric/review.py"))
TINY = run_path(str(HERE.parent / "client/grade.py"))
need = CPU["need"]
CPU_COMPACT = "4f0009aedf2a685b3c75e4b32149f092be1ac7974fe1be8755598d1d15a41b66"


def references(c110_parent, stock_file, cpu_d0, cpu_d1):
    """Use all original receipts; CPU D1 is an intervention, not a fourth gold."""
    refs, labels = CPU["references"](c110_parent, stock_file)
    path = HERE.parents[1] / "cpu_numeric/physical-pair.json"
    compact = json.loads(CPU["pinned"](path, CPU_COMPACT))
    copies = []
    for label, folder in (("D0", cpu_d0), ("D1", cpu_d1)):
        authority = compact["arms"][label]
        rows, status = CPU["candidate"](label, folder, authority["physical_sha256"])
        need(status == "PASS_IK_CPU_NUMERIC_ARM" and set(rows) == {15, 16}, "CPU reference")
        need(
            all(
                CPU["digest"](r) == authority["logits_sha256"][f"pos{p}.f32"]
                for p, r in rows.items()
            ),
            "CPU gold fingerprint",
        )
        copies.append(rows)
    need(copies[0] == copies[1] and len(labels) == 6, "reference disagreement")
    return {**refs, "ik_cpu": copies[0]}


def cut(reference, candidate, vocab=CPU["VOCAB"]):
    """Compare one complete row; signed zero changes its F32 word with zero real error."""
    need(vocab > 0 and len(reference) == len(candidate) == 4 * vocab, "complete F32 rows")
    ref = CPU["describe"](reference, vocab)
    cand = CPU["describe"](candidate, vocab)
    words = zip(
        struct.iter_unpack("<I", reference), struct.iter_unpack("<I", candidate), strict=True
    )
    first = None
    count = 0
    for index, (x, y) in enumerate(words):
        if x != y:
            if first is None:
                first = index
            count += 1
    out = dict(
        reference=ref,
        candidate=cand,
        changed_words=count,
        first_changed_index=first,
        bitwise=reference == candidate,
        mean_abs=None,
        max_abs=None,
        rmse=None,
        unique_greedy_equal=False,
        top5_equal=None,
    )
    if ref["finite"] and cand["finite"]:
        left = struct.unpack(f"<{vocab}f", reference)
        right = struct.unpack(f"<{vocab}f", candidate)
        delta = [abs(a - b) for a, b in zip(left, right, strict=True)]
        out.update(
            mean_abs=math.fsum(delta) / vocab,
            max_abs=max(delta),
            rmse=math.sqrt(math.fsum(x * x for x in delta) / vocab),
            unique_greedy_equal=(
                ref["max_ties"] == cand["max_ties"] == 1 and ref["top5"][0] == cand["top5"][0]
            ),
            top5_equal=ref["top5"] == cand["top5"],
        )
    return out


def bank_sites(records, capacity):
    """Validate the shared bank after the transport verifier reconciles every role."""
    need(capacity in (161, 288), "bank capacity")
    expected = [(phase, layer) for phase in ("prefill", "teacher") for layer in range(36)]
    state = {}
    sites = {}
    for site, row in zip_longest(expected, records):
        need(
            site is not None and isinstance(row, dict) and site == (row["phase"], row["layer"]),
            "missing, repeated or unordered site",
        )
        phase, layer = site
        width = 16 if phase == "prefill" and layer < 35 else 1
        ids, slots = row["logical"], row["physical"]
        need(len(ids) == len(slots) == 4 * width, "rank width")
        need(
            all(type(e) is int and 0 <= e < 128 for e in ids)
            and all(type(s) is int and 0 <= s < capacity for s in slots)
            and all(len(set(ids[i : i + 4])) == 4 for i in range(0, len(ids), 4)),
            "rank ID or slot",
        )
        # Each arm has one shared bank. Distinguish logical IDs from different layers.
        keys = [(layer, e) for e in ids]
        fills = {}
        for e, slot in row["fills"]:
            key = (layer, e)
            need(
                type(e) is int and type(slot) is int and key not in fills, "duplicate/invalid fill"
            )
            fills[key] = slot
        TINY["bank_step"](keys, slots, fills, state, capacity)
        sites[site] = (tuple(ids), tuple(slots), frozenset(fills))
    return sites


def compare_placements(records288, records161):
    a, b = bank_sites(records288, 288), bank_sites(records161, 161)
    first = None
    different_slots = different_service = 0
    for (phase, layer), (ids, slots, fills) in a.items():
        ids_b, slots_b, fills_b = b[phase, layer]
        for index, (e, other, s, other_slot) in enumerate(
            zip(ids, ids_b, slots, slots_b, strict=True)
        ):
            if e != other and first is None:
                pos = 16 if phase == "teacher" else 15 if layer == 35 else index // 4
                first = dict(phase=phase, layer=layer, position=pos, rank=index % 4)
            if e == other and s != other_slot:
                different_slots += 1
        common = {(layer, e) for e in set(ids) & set(ids_b)}
        different_service += len(common & (fills ^ fills_b))
    return dict(
        sites=len(a),
        quartets=sum(len(ids) // 4 for ids, _, _ in a.values()),
        ordered_routes_equal=first is None,
        first_route_difference=first,
        different_slots_at_same_rank=different_slots,
        different_hit_fill_at_common_site_keys=different_service,
        distinguished=different_slots > 0 or different_service > 0,
    )


def numeric_decision(rows, places, expected=(3659, 3992)):
    """The supervisor still owns authentication, device placement and resource/closure checks."""
    need(
        set(rows) == {15, 16} and places["quartets"] == 597 and places["sites"] == 72,
        "incomplete paired contrast",
    )
    for pos, top in zip((15, 16), expected, strict=True):
        for label in ("reference", "candidate"):
            d = rows[pos][label]
            if not d["finite"] or d["max_ties"] != 1 or d["top5"][0] != top:
                return "FAIL_FINITE_OR_GREEDY"
    if not places["ordered_routes_equal"] or not all(r["bitwise"] for r in rows.values()):
        return "NO_GO_BANK_SIZE_PARITY"
    if not places["distinguished"]:
        return "INCONCLUSIVE_NO_PLACEMENT_OR_SERVICE_CONTRAST"
    return "PASS_PAIRED_NUMERIC_COMPONENT"
