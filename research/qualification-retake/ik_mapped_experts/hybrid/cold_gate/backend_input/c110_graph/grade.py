"""Check each actual source address, learned slot, ordered rank and complete C110 row."""

from bisect import bisect_right
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
HYBRID = HERE.parents[2]
REAL = run_path(str(HYBRID / "driver_62073/real.py"))
A, FR, OFF, G, need = (REAL[k] for k in ("A", "FR", "OFF", "G", "need"))
TINY = run_path(str(HERE.parent / "tiny_graph/grade.py"))
HISTORY = "97291f30c38c5f29fe9c5a6a08aaa3fd0d21b7132da486e2ca54a09244c1b502"
BANK = "BANK288"
CAPACITY = 648155136
SOURCES = {
    "ORIGINAL_OFF": (None, "OFF"),
    "DIRECT_OFF": ("DIRECT", "OFF"),
    "PREAD_ON": ("PREAD_RANDOM", "ON"),
    "PREAD_OFF": ("PREAD_RANDOM", "OFF"),
}


def history(folder, plan):
    r = A["receipt"](folder / "receipt.json", HISTORY)
    need(r["status"] == "PASS_CALLBACK_OFF_TWO_CUTS" and r["model_starts"] == 4, "C110 authority")
    historical = {}
    for selector in ("ON", "OFF"):
        label = selector + "/" + BANK
        parent = folder / label
        arm = A["receipt"](parent / "receipt.json", r["arms"][label]["receipt_sha256"])
        need(
            FR["inventory"](parent) == arm["raw_sha256"] == r["arms"][label]["raw_sha256"],
            "C110 raw",
        )
        out = (parent / "raw/stdout").read_text()
        if selector == "ON":
            grade = G["check_arm"](
                BANK, out, (parent / "raw/stderr").read_text(), parent / "native", plan
            )
            on = grade
        else:
            grade = OFF["grade"](BANK, parent, plan, folder / "ON", on)
        need(OFF["R"]["serial"](grade) == arm["grade"], "historical grade")
        historical[selector] = TINY["schedule"](out)
    return on, historical


def audit_source(raw, source, native, model, plan, ledger):
    entries = []
    for name, (start, length, _typ) in G["CAP"]["tensor_plan"](plan).items():
        match = OFF["T"]["FILE_NAME"].fullmatch(name)
        if match:
            entries.append((start, start + length, (int(match[1]), match[2])))
    entries.sort()
    starts = [row[0] for row in entries]
    need(
        len(entries) == 108
        and all(a[1] <= b[0] for a, b in zip(entries, entries[1:], strict=False)),
        "expert tensors",
    )

    def slice_for(off, n):
        i = bisect_right(starts, off) - 1
        if i < 0 or not 0 < n <= entries[i][1] - off:
            return None
        return entries[i][2], off - entries[i][0]

    sites, routes = [], {}
    for row in ledger:
        phase = OFF["T"]["PHASE"][row["phase"]]
        key = phase, row["layer"]
        need(key not in routes, "duplicate control site")
        sites.append((*key, len(row["logical"]) * 4))
        routes[key] = ",".join(map(str, row["logical"]))
    order = [(phase, layer) for phase in (3, 4) for layer in range(36)]
    need([site[:2] for site in sites] == order, "C110 order")
    return TINY["audit"](
        raw,
        source,
        native,
        model,
        sites=sites,
        capacity=CAPACITY,
        weight_slice=slice_for,
        vma_files={3: "prefill.maps", 4: "teacher.maps"},
        expected_bytes={3: 14752627200, 4: 1692057600},
        reference_routes=routes,
    )


def evaluate(label, directory, previous, model, plan, on, schedules, refs):
    source, selection = SOURCES[label]
    native = directory / "native"
    raw, log = ((directory / "raw" / f).read_text() for f in ("stdout", "stderr"))
    need(
        [s for s in raw.splitlines() if s.startswith("CB_EVAL ")] == ["CB_EVAL " + selection],
        "observer",
    )
    marker = "BANK_MODE " + source if source else None
    need(
        [s for s in raw.splitlines() if s.startswith("BANK_MODE ")] == ([marker] if marker else []),
        "source selector",
    )
    if source:
        # Validate the transport journal first. The selector is a separate startup record.
        audit_raw = "\n".join(s for s in raw.splitlines() if s != marker) + "\n"
        view, covered = audit_source(audit_raw, source, native, model, plan, on["ledger"])
        covered["raw_sha256"] = A["sha"](directory / "raw/stdout")
        need(
            covered["bank_sets"] == covered["physical_copies"]
            and covered["scratch_high_water_B"] == CAPACITY,
            "physical copies or scratch",
        )
    else:
        need(not any(s.startswith("BANK_") for s in raw.splitlines()), "original is instrumented")
        view, covered = raw, None
    need(
        TINY["schedule"](raw) == schedules[selection], "SET order, physical slots or consumer ranks"
    )
    previous_native = previous / "ON" / BANK / "native"
    rows = OFF["compare_rows"](native, G["rows_from_grade"](previous_native, on))
    need(
        set(rows) == {"15", "16"} and all(v["bitwise"] for v in rows.values()), "full F32 mismatch"
    )
    if selection == "ON":
        g = G["check_arm"](BANK, view, log, native, plan)
        need(
            g["status"] == "PASS_IK_GPU_BANK_ARM"
            and g["ledger"] == on["ledger"]
            and (g["consumer_ops"], g["sites"], g["ordered_quartets"]) == (432, 72, 597),
            "routed graph",
        )
    else:
        g = OFF["grade"](BANK, directory, plan, previous / "ON", on, logical_stdout=view)
        need(g["status"] == "PASS_CALLBACK_OFF_TWO_CUTS", "observed OFF execution")
    externals = {key: OFF["compare_rows"](native, other) for key, other in refs.items()}
    return dict(
        status="PASS_C110_BANK_INPUT_ARM",
        rows=rows,
        physical=covered,
        grade=g,
        independent_references=externals,
    )
