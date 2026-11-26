"""Reopen each transfer against independent byte references before comparing the two orders."""

import argparse
import hashlib
import json
import os
from pathlib import Path

ORDERS = {"DIRECT_FIRST": ("DIRECT", "STAGED"), "STAGED_FIRST": ("STAGED", "DIRECT")}
READ_ORDERS = {
    "RANGE_DIRECT_FIRST": ("DIRECT", "PREAD_SEQ", "PREAD_RANDOM"),
    "RANGE_RANDOM_FIRST": ("PREAD_RANDOM", "PREAD_SEQ", "DIRECT"),
}
LAYER_ORDERS = {
    "LAYER_DIRECT_FIRST": ("DIRECT", "PREAD_RANDOM"),
    "LAYER_RANDOM_FIRST": ("PREAD_RANDOM", "DIRECT"),
}
SEQUENCES = {"scratch": ORDERS, "pread": READ_ORDERS, "layer": LAYER_ORDERS}
STATUS = {
    "scratch": "MEASURED_COLD_GATE_TRANSFER",
    "pread": "MEASURED_COLD_RANGE_READ",
    "layer": "MEASURED_COLD_LAYER_READ",
}
REFERENCE = "2f47da616820c239441b4a94ad4f2344ddc7393d1dad8a6c7a4f05cbb4ec4deb"
LAYER_REFERENCE = "4a52e83b2bc55a9fd266fb769c44673ea5a60856db4d4b1f898d225be661d143"


def require(test, reason):
    if not test:
        raise ValueError(reason)


def digest(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def one(path, mode, ref, *, late_cut=False):
    v = json.loads(path.read_bytes())
    expected = [x["sha256"] for x in ref["sets"]]
    banks = 3 if "tensors" in ref else 1
    require(
        v["mode"] == mode
        and v["verified"] == expected
        and len(expected) == 33 * banks
        and v["guards_B"] == 8192 * banks
        and v["resident_before"] == 0
        and 0 < v["resident_after"] <= v["tensor_pages"],
        "wrong coverage, source state or transfer identity",
    )
    events = v["events_ns"]
    last = acquisition = submission = 0
    for start, copied, submitted in events:
        require(last <= start <= copied <= submitted, "nonmonotone SET clock")
        acquisition += copied - start
        submission += submitted - copied
        last = submitted
    total, drain = v["total_ns"], v["drain_ns"]
    require(
        len(events) == len(expected)
        and last <= v["issued_ns"] == total - drain
        and total > 0
        and drain >= 0,
        "missing service or drain",
    )
    delta = {k: v["after"][k] - v["before"][k] for k in ("namespace_B", "scope_B", "pid_B")}
    require(
        delta == v["delta"]
        and 0 < delta["namespace_B"] <= 6 << 30
        and delta["scope_B"] > 0
        and delta["pid_B"] >= 0,
        "read evidence",
    )
    result = dict(
        total_ns=total,
        source_ns=acquisition,
        submit_ns=submission,
        drain_ns=drain,
        loop_ns=total - acquisition - submission - drain,
        reads=delta,
        source_resident_pages_before=0,
        source_resident_pages_after=v["resident_after"],
        tensor_pages=v["tensor_pages"],
        verify_ns=v["check_ns"],
        verified_bytes=ref["payload_B"],
    )
    if late_cut:
        advice = os.POSIX_FADV_RANDOM if mode == "PREAD_RANDOM" else os.POSIX_FADV_SEQUENTIAL
        late = {k: v["late"][k] - v["before"][k] for k in delta}
        require(
            v["fd_advice"] == advice
            and v["pread_calls"] == (len(expected) if mode.startswith("PREAD_") else 0)
            and v["late_since_drain_ns"] >= 100_000_000 + v["check_ns"]
            and all(late[k] >= delta[k] for k in delta)
            and late["namespace_B"] <= 6 << 30,
            "wrong range read or missing late window",
        )
        result.update(
            late_reads=late,
            late_since_drain_ns=v["late_since_drain_ns"],
            pread_calls=v["pread_calls"],
            fd_advice=advice,
        )
    if banks == 3:
        total = {
            role: (t["start"] % 4096 + t["bytes"] + 4095) // 4096
            for role, t in ref["tensors"].items()
        }
        before, after = v["pages_before"], v["pages_after"]
        require(
            set(total) == set(before) == set(after) == {"gate", "up", "down"}
            and total == v["pages_per_tensor"]
            and sum(total.values()) == v["tensor_pages"]
            and all(before[k] == 0 and 0 < after[k] <= total[k] for k in total)
            and sum(after.values()) == v["resident_after"],
            "individual matrix residency",
        )
        result.update(pages_before=before, pages_after=after, pages_per_tensor=total)
    return result


def decide(orders, baseline="DIRECT", candidate="STAGED", *, minimum_bytes_saved=0):
    pairs = []
    require(len(orders) == 2, "two orders required")
    for order, rows in orders.items():
        d, s = rows[baseline], rows[candidate]
        pairs.append(
            dict(
                order=order,
                saved_ns=d["total_ns"] - s["total_ns"],
                scope_bytes_saved=d["reads"]["scope_B"] - s["reads"]["scope_B"],
            )
        )
    if all(p["saved_ns"] > 0 and p["scope_bytes_saved"] >= minimum_bytes_saved for p in pairs):
        decision = "GO"
    elif all(p["saved_ns"] <= 0 for p in pairs):
        decision = "NO_GO"
    else:
        decision = "INCONCLUSIVE"
    return decision, pairs


def read_contrasts(orders):
    result = {}
    for base, candidate in (
        ("DIRECT", "PREAD_RANDOM"),
        ("DIRECT", "PREAD_SEQ"),
        ("PREAD_SEQ", "PREAD_RANDOM"),
    ):
        decision, pairs = decide(orders, base, candidate, minimum_bytes_saved=1)
        result[base + "_to_" + candidate] = dict(decision=decision, pairs=pairs)
    return result


def reopen(family, family_sha, reference):
    require(
        digest(family / "receipt.json") == family_sha,
        "family digest",
    )
    ref = json.loads(reference.read_bytes())
    r = json.loads((family / "receipt.json").read_bytes())
    study = r["authority"].get("study", "scratch")
    sequence = SEQUENCES[study]
    ref_sha = LAYER_REFERENCE if study == "layer" else REFERENCE
    require(digest(reference) == ref_sha, "reference digest")
    raw = {
        str(p.relative_to(family)): digest(p)
        for p in sorted(family.rglob("*"))
        if p.is_file() and p != family / "receipt.json"
    }
    require(
        r["status"] == STATUS[study]
        and set(r["arms"]) == set(sequence)
        and r["raw_sha256"] == raw
        and r["authority"]["reference_sha256"] == ref_sha
        and r["swap_peak_B"] == 0
        and r["memory_peak_B"] < (3584 if study == "layer" else 1536) << 20,
        "family integrity or resources",
    )
    orders, life = {}, {}
    for order, modes in sequence.items():
        arm = r["arms"][order]
        require(
            arm["observed_handoffs"] == 3
            and arm["returncode"] == 0
            and arm["child_gone"]
            and arm["starts"] == 1
            and arm["sampled_vram_mib_max"] < 1536,
            "child lifecycle",
        )
        orders[order] = {
            m: one(family / order / "native" / (m + ".json"), m, ref, late_cut=study != "scratch")
            for m in modes
        }
        require(orders[order] == arm["measurements"], "recorded cut differs")
        life[order] = dict(wall_s=arm["wall_s"], peak_vram_MiB=arm["sampled_vram_mib_max"])
    contrasts = {}
    if study == "pread":
        contrasts = read_contrasts(orders)
        require(contrasts == r["contrasts"], "secondary contrasts differ")
        primary = contrasts["DIRECT_to_PREAD_RANDOM"]
        decision, pairs = primary["decision"], primary["pairs"]
    elif study == "layer":
        decision, pairs = decide(orders, "DIRECT", "PREAD_RANDOM", minimum_bytes_saved=1)
    else:
        decision, pairs = decide(orders)
    require((decision, pairs) == (r["decision"], r["pairs"]), "recorded decision differs")
    report = dict(
        status=STATUS[study],
        decision=decision,
        scope="THREE_C110_BANKS" if study == "layer" else "ONE_C110_GATE",
        family_sha256=family_sha,
        reference_sha256=ref_sha,
        orders=orders,
        pairs=pairs,
        processes=life,
        memory_peak_B=r["memory_peak_B"],
        swap_peak_B=r["swap_peak_B"],
        commit=r["authority"]["commit"],
        tree=r["authority"]["tree"],
        sets=len(ref["sets"]),
        payload_B=ref["payload_B"],
        scratch_B=ref["scratch_B"],
        model_forwards=0,
        product_requests=0,
        integrated_energy_J=None,
    )
    if contrasts:
        report["contrasts"] = contrasts
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("family", "reference", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        out = reopen(a.family, a.family_sha256, a.reference)
    except Exception as exc:
        out = dict(status="FAIL_PRESERVED", reason=str(exc))
    (a.new_output_dir / "review.json").write_text(json.dumps(out, sort_keys=True, indent=2) + "\n")
    print(out["status"], out.get("decision", out.get("reason", "")))
    raise SystemExit(out["status"] == "FAIL_PRESERVED")
