"""Validate a single long C294 arm before the next process can start."""

import hashlib
import json
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(QUAL / "warm_routes40"), str(QUAL / "prefix_observer"), str(ROOT / "tools")]
from r2_causal_gate import initial_identity, inspect  # noqa: E402
from run_bounded import sha256  # noqa: E402
from witness import compare_tpr, read, require  # noqa: E402

C280 = "c280-r2-three-way-causal-cost-20261005"
MANIFEST = "c59d23640169f6c4b4ddf07956d8bca6707650776b3ab6a516632c4cba102c55"
FIXTURE = "ffcd2da79b579960cf43cfb3f696de6f48d50723cfa77ef36a9d5e7fbd48d14a"
REF = runpy.run_path(str(QUAL / "warm_route_reference/verify.py"))
ORDER = [("nominal153", "OFF"), ("nominal153", "ON"), ("code153", "ON"), ("code153", "OFF")]


def load(p):
    return json.loads(p.read_bytes())


def state(value):
    return hashlib.sha256(
        json.dumps(
            initial_identity({"initial": value}), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def inputs(hist):
    fixture = (
        hist / "c276-post-c274-r2-causal-qualification-20261005T204839Z/development-inputs.json"
    )
    require(sha256(fixture) == FIXTURE, "supplied IDs hash")
    specs = load(fixture)
    mp = ROOT / "results" / C280 / "raw-manifest.json"
    require(sha256(mp) == MANIFEST, "C280 manifest changed")
    sealed = {x["path"]: x for x in load(mp)["files"]}
    references = {}
    for case, runs in (("nominal153", (1, 6)), ("code153", (7, 12))):
        rows = []
        for i in runs:
            rel = Path("raw") / f"c280-{i}-r0.native"
            d = hist / C280 / rel
            for name in ("all33.logits.f32", "initial.json", "result.json"):
                path = d / name
                record = sealed[str(rel / name)]
                require(
                    path.stat().st_size == record["bytes"] and sha256(path) == record["sha256"],
                    "C280 missing or corrupt",
                )
            val, digest = inspect(d, specs[case], "R0", case)
            require(val["initial"] == load(d / "initial.json"), "C280 P differs from initial")
            rows.append(
                {
                    "gold": digest,
                    "P": state(val["initial"]),
                    "F": state(val["final"]),
                    "winners": val["native_argmax_ids"],
                }
            )
        require(rows[0] == rows[1], "independent C280 runs disagree")
        references[case] = rows[0]
    return fixture, specs, references


def validate(native, case, mode, spec, reference, prior):
    result, full = inspect(native, spec, "R0", case)
    require(
        result["trace"] is False
        and result["trace_events"] == 0
        and result["transport"] == "ORIGINAL"
        and not result["store_manifest_env"],
        "C294 window or transport changed",
    )
    require(
        (native / "events.tsv").read_text().splitlines() == [REF["boundary"].HEADER],
        "unrequested C294 journal",
    )
    require(result["initial"] == load(native / "initial.json"), "P differs from repeated initial")
    require(
        (full, result["native_argmax_ids"]) == (reference["gold"], reference["winners"]),
        "gold vectors or argmax differ",
    )
    require(
        (state(result["initial"]), state(result["final"])) == (reference["P"], reference["F"]),
        "P/F state mismatch",
    )
    for k in ("initial", "final"):
        REF["boundary"].slots(result[k])
    wrtpath = native / "routed-witness.bin"
    require(0 < wrtpath.stat().st_size <= 1024**2, "witness missing or oversized")
    wrt = wrtpath.read_bytes()
    graphs, rows = read(wrt)
    call_lengths = result["external_prefill_calls"] + [1] * 32
    expected = []
    pos = 0
    for call, length in enumerate(call_lengths, 1):
        for ub, offset in enumerate(range(0, length, 32), 1):
            expected.append((call, ub, tuple(range(pos + offset, pos + min(length, offset + 32)))))
        pos += length
    require(expected == graphs, "positions, call order or ubatches changed")
    require(len(rows) == 35 * pos + len(call_lengths), "routed group count")
    ordered = REF["check_witness"](
        case, ((call - 9, layer, pos, ids) for call, _, layer, pos, ids in rows if call >= 10)
    )
    tpr = native / "prefix-routes.bin"
    names = [
        "routed-witness.bin",
        "boundary-i.json",
        "initial.json",
        "result.json",
        "all33.logits.f32",
        "events.tsv",
    ]
    if mode == "ON":
        import journal

        expected_bytes = 334033 if case == "nominal153" else 320439
        require(tpr.stat().st_size == expected_bytes, "wrong TPR1 size")
        data = tpr.read_bytes()
        require(
            [x for x in journal.records(data) if x[0] == "cut"]
            == [("cut", "P", 8), ("cut", "I", 9)],
            "TPR cut",
        )
        compare_tpr(wrt, data)
        names.append("prefix-routes.bin")
    else:
        require(not tpr.exists(), "OFF emitted TPR1")
    boundary_i = runpy.run_path(str(QUAL / "warm_routes40/boundary.py"))["verify"](
        case, native / "boundary-i.json"
    )
    require(boundary_i["reserved_object_bytes"] == 23064, "unexpected boundary buffer size")
    require(not list(native.glob("*.partial")), "incomplete publication")
    hashes = {n: sha256(native / n) for n in names}
    if prior is not None:
        require(
            prior["case"] == case
            and prior["mode"] != mode
            and prior["native_sha256"]["routed-witness.bin"] == hashes["routed-witness.bin"]
            and prior["I_sha256"] == boundary_i["slot_vector_sha256"],
            "OFF/ON graphs, ranks or I diverged",
        )
    return {
        "status": "PASS_WARM_ROUTE_ARM",
        "case": case,
        "mode": mode,
        "native_sha256": hashes,
        "I_sha256": boundary_i["slot_vector_sha256"],
        "I_copy_ns": boundary_i["copy_ns"],
        "I_resident_slots": boundary_i["resident_slots"],
        "P_sha256": reference["P"],
        "F_sha256": reference["F"],
        "decode_sha256": ordered,
        "groups": len(rows),
        "ubatches": len(graphs),
    }
