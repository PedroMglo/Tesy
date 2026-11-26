"""Grade retained rows, KV and physical transfers in a complete C110 callback-OFF arm."""

import re
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
T = run_path(str(HERE / "transport.py"))
G, need = T["G"], T["need"]
R = run_path(str(HERE.parent / "review.py"))
OPS = R["RUN"]["OPS"]
CALLBACK_EVENTS = ("ROUTE ", "NODE ", "BIAS_READ ", "RANK_VIEW ")
CENSUS = (
    "CONTEXT 8192 1 256 32 0 0",
    "KV_CELLS 8192",
    "KV 15 16",
    "ROW 15 201088 3659 1",
    "KV 16 17",
    "ROW 16 201088 3992 1",
)
GEOMETRY = ("CONTEXT ", "KV_CELLS ", "KV ", "ROW ")


def reference(family, plan):
    root = R["checked"](family / "receipt.json", R["ROOT_SHA"])
    need(root["status"] == "PASS_BANK_SIZE_PARITY_TWO_CUTS", "ON family")
    grades = {}
    for mode in R["RUN"]["MODES"]:
        p = family / mode
        old = R["checked"](p / "receipt.json", root["arms"][mode]["receipt_sha256"])
        need(R["RUN"]["inventory"](p) == old["raw_sha256"], "ON raw drift")
        grade = G["check_arm"](
            mode, (p / "raw/stdout").read_text(), (p / "raw/stderr").read_text(), p / "native", plan
        )
        need(R["serial"](grade) == old["grade"], "ON arm grade")
        grades[mode] = grade
    pair = G["check_pair"](
        family / "BANK288/native", grades["BANK288"], family / "BANK161/native", grades["BANK161"]
    )
    need(R["serial"](pair) == root["pair"], "ON pair grade")
    return grades


def compare_rows(native, reference_rows):
    return {
        str(pos): G["C"]["cut"](ref, (native / f"pos{pos}.f32").read_bytes())
        for pos, ref in reference_rows.items()
    }


def decision(rows, service_match):
    need(set(rows) == {"15", "16"}, "both cuts required")
    if not all(row["bitwise"] for row in rows.values()):
        return "NO_GO_CALLBACK_PARITY"
    return "PASS_CALLBACK_OFF_TWO_CUTS" if service_match else "INCONCLUSIVE_SERVICE_CONTRAST"


def grade(mode, folder, plan, family, on, *, logical_stdout=None):
    native = folder / "native"
    # A caller using staged sources first authenticates the physical CUDA copies.
    text = (folder / "raw/stdout").read_text() if logical_stdout is None else logical_stdout
    lines = text.splitlines()
    log = (folder / "raw/stderr").read_text()
    need(
        [r for r in lines if r.startswith("CB_EVAL ")] == ["CB_EVAL OFF"]
        and not any(r.startswith(CALLBACK_EVENTS) for r in lines),
        "unexpected callback witness",
    )
    need(
        [r for r in lines if r.startswith("STATUS ")] == ["STATUS COMPLETED_IK_GPU_BANK_CUTS"]
        and [r for r in lines if r.startswith(GEOMETRY)] == list(CENSUS),
        "incomplete native cuts",
    )
    need(
        [r for r in lines if r.startswith("MAP ")] == ["MAP 0 63387346208 1 1"]
        and not any(int(r.split()[3]) == 3 for r in lines if r.startswith(("MAD ", "POSIX "))),
        "unexpected mapping or prefetch",
    )
    slots = G["SLOTS"][mode]
    tensors, _, _ = G["startup"](lines, log, plan, slots)
    memory = G["profile"](lines, slots)
    ref = G["rows_from_grade"](family / mode / "native", on)
    rows = compare_rows(native, ref)
    copies = T["compare"](lines, tensors, slots, on["ledger"])
    submitted = Counter()
    seen = set()
    for r in lines:
        if r.startswith("SUBMIT "):
            _, phase, ptr, dev, rc = r.split()
            need(
                phase in ("3", "4")
                and int(ptr) > 0
                and rc == "0"
                and dev in ("CPU", "CUDA0")
                and (phase, ptr) not in seen,
                "failed or duplicate submission",
            )
            seen.add((phase, ptr))
            submitted[phase + ":" + dev] += 1
    buckets = {}
    for match in re.finditer(
        r"(ubatch <= 8|ubatch 9-32) hits=(\d+) gpu_fills=(\d+) cpu_serviced_unique_misses=(\d+)"
        r" unique_keys=(\d+) unique_key_hit_rate=[0-9.]+% logical_uploaded_bytes=(\d+)",
        log,
    ):
        label, *counts = match.groups()
        need(label not in buckets, "repeated width")
        buckets[label] = list(map(int, counts))
    need(len(buckets) == 2, "missing service counters")
    expected = Counter()
    for row in on["ledger"]:
        label = "ubatch <= 8" if len(row["logical"]) == 4 else "ubatch 9-32"
        unique = len(set(row["logical"]))
        expected[label, "unique"] += unique
        expected[label, "fills"] += len(row["fills"])
    width_match = all(
        buckets[label]
        == [
            expected[label, "unique"] - expected[label, "fills"],
            expected[label, "fills"],
            0,
            expected[label, "unique"],
            expected[label, "fills"] * 3 * G["SLAB"],
        ]
        for label in buckets
    )
    topology = dict(submitted) == {p + ":" + d: 108 for p in ("3", "4") for d in ("CPU", "CUDA0")}
    return dict(
        status=decision(rows, copies["match"] and width_match and topology),
        rows=rows,
        source_and_slot=copies,
        backend_submissions=dict(submitted),
        submission_counts_match=topology,
        widths=buckets,
        width_match=width_match,
        memory=memory,
        individual_route_order="UNOBSERVED_OFF",
    )
