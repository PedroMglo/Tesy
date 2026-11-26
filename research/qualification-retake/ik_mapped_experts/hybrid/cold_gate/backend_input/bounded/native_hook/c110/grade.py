"""Authenticate each native cache transfer against the two qualified C110 source paths."""

from bisect import bisect_right
from collections import defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
N = run_path(str(HERE.parent / "grade.py"))
P = run_path(str(HERE.parents[2] / "c110_graph/price/grade.py"))
C, need = P["PARENT"], P["need"]
OFF, G, A, FR = (C[k] for k in ("OFF", "G", "A", "FR"))
CAP = C["CAPACITY"]
MODES = ("DIRECT", "PREAD_RANDOM")


def reference(numerical, plan):
    service, hashes = P["reference"](numerical)
    file_name = OFF["T"]["FILE_NAME"]
    weights = sorted(
        (start, start + length, name, int(m[1]))
        for name, (start, length, _) in G["CAP"]["tensor_plan"](plan).items()
        if (m := file_name.fullmatch(name))
    )
    need(
        len(weights) == 108
        and all(a[1] <= b[0] for a, b in zip(weights, weights[1:], strict=False)),
        "weights",
    )
    starts = [s[0] for s in weights]
    ids = {}
    batches = defaultdict(list)
    for line in service.splitlines():
        s = line.split()
        phase, gen = map(int, s[1:3])
        layer = (gen - 1) % 36
        need(0 < gen <= 72 and phase == (3 if gen <= 36 else 4), "generation")
        if s[0] == "IDS":
            need(gen not in ids, "duplicate rank vector")
            ids[gen] = ("IDS", gen, layer, *map(int, s[3:]))
        else:
            layer_ref, offset, dest, n = map(int, (s[3], *s[5:]))
            i = bisect_right(starts, offset) - 1
            low, high, name, weight_layer = weights[i]
            need(
                s[0] == "SET"
                and low <= offset < offset + n <= high
                and layer_ref == weight_layer == layer,
                "authoritative source tensor",
            )
            batches[gen].append(("SET", gen, layer, name, s[4], offset, dest, n))
    need(
        len(ids) == 72
        and sum(len(e) - 3 for e in ids.values()) == 597 * 4
        and len(batches[72]) == 6,
        "rank vectors or final batch",
    )
    events = [r for gen in range(1, 73) for r in [ids[gen], *batches[gen]]]
    _, drains, peak = N["layout"](events, CAP)
    need(drains == 0 and peak == CAP, "frozen pressure prediction")
    return events, hashes


def evaluate(mode, folder, previous, model, plan, on, schedules, refs, gold):
    events, hashes = gold
    raw = (folder / "raw/stdout").read_text()
    log = (folder / "raw/stderr").read_text()
    origins = {}
    for s in N["G"]["records"](raw, "PLACE"):
        if OFF["T"]["FILE_NAME"].fullmatch(s[0]):
            need(s[0] not in origins and (s[1], s[3], s[6]) == ("39", "1", "CPU"), "matrix VMA")
            origins[s[0]] = int(s[5]), int(s[2]), int(s[4])
    need(
        len(origins) == 108 and not any(line.startswith("BANK_") for line in raw.splitlines()),
        "original observer or model placement",
    )
    native = folder / "native"
    view, proof = N["audit"](
        mode,
        raw,
        log,
        native,
        model,
        events,
        capacity=CAP,
        layers=36,
        origins=origins,
        maps={3: "prefill.maps", 4: "teacher.maps"},
    )
    need(N["A"]["schedule"](view) == schedules["OFF"], "numerical control service order")
    grade = OFF["grade"](C["BANK"], folder, plan, previous / "ON", on, logical_stdout=view)
    need(grade["status"] == "PASS_CALLBACK_OFF_TWO_CUTS", "numerical or transport mismatch")
    for pos, digest in hashes.items():
        need(A["sha"](native / f"pos{pos}.f32") == digest, "independent full row")
    phase_bytes = [
        sum(e[7] for e in events if e[0] == "SET" and (e[1] <= 36) == prefill)
        for prefill in (True, False)
    ]
    need(phase_bytes == [14752627200, 1692057600], "payload")
    external = {k: OFF["compare_rows"](native, other) for k, other in refs.items()}
    return dict(
        status="PASS_NATIVE_C110_ARM",
        grade=grade,
        physical=proof,
        logits_sha256=hashes,
        ordered_quartets=597,
        phase_bytes=phase_bytes,
        sets_in_final_generation=6,
        independent_references=external,
    )
