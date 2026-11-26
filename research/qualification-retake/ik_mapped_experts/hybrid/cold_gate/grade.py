"""Reopen each transfer against independent byte references before comparing the two orders."""

import argparse
import hashlib
import json
from pathlib import Path

ORDERS = {"DIRECT_FIRST": ("DIRECT", "STAGED"), "STAGED_FIRST": ("STAGED", "DIRECT")}
REFERENCE = "2f47da616820c239441b4a94ad4f2344ddc7393d1dad8a6c7a4f05cbb4ec4deb"


def require(test, reason):
    if not test:
        raise ValueError(reason)


def digest(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def one(path, mode, ref):
    v = json.loads(path.read_bytes())
    expected = [x["sha256"] for x in ref["sets"]]
    require(
        v["mode"] == mode
        and v["verified"] == expected
        and len(expected) == 33
        and v["guards_B"] == 8192
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
    return dict(
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


def decide(orders):
    pairs = []
    for order in ORDERS:
        d, s = (orders[order][mode] for mode in ("DIRECT", "STAGED"))
        pairs.append(
            dict(
                order=order,
                saved_ns=d["total_ns"] - s["total_ns"],
                scope_bytes_saved=d["reads"]["scope_B"] - s["reads"]["scope_B"],
            )
        )
    if all(p["saved_ns"] > 0 and p["scope_bytes_saved"] >= 0 for p in pairs):
        decision = "GO"
    elif all(p["saved_ns"] <= 0 for p in pairs):
        decision = "NO_GO"
    else:
        decision = "INCONCLUSIVE"
    return decision, pairs


def reopen(family, family_sha, reference):
    require(
        digest(reference) == REFERENCE and digest(family / "receipt.json") == family_sha,
        "family or reference digest",
    )
    ref = json.loads(reference.read_bytes())
    r = json.loads((family / "receipt.json").read_bytes())
    raw = {
        str(p.relative_to(family)): digest(p)
        for p in sorted(family.rglob("*"))
        if p.is_file() and p != family / "receipt.json"
    }
    require(
        r["status"] == "MEASURED_COLD_GATE_TRANSFER"
        and r["raw_sha256"] == raw
        and r["authority"]["reference_sha256"] == REFERENCE
        and r["swap_peak_B"] == 0
        and r["memory_peak_B"] < 1536 << 20,
        "family integrity or resources",
    )
    orders, life = {}, {}
    for order, modes in ORDERS.items():
        arm = r["arms"][order]
        require(
            arm["observed_handoffs"] == 3
            and arm["returncode"] == 0
            and arm["child_gone"]
            and arm["starts"] == 1
            and arm["sampled_vram_mib_max"] < 1536,
            "child lifecycle",
        )
        orders[order] = {m: one(family / order / "native" / (m + ".json"), m, ref) for m in modes}
        require(orders[order] == arm["measurements"], "recorded cut differs")
        life[order] = dict(wall_s=arm["wall_s"], peak_vram_MiB=arm["sampled_vram_mib_max"])
    decision, pairs = decide(orders)
    require((decision, pairs) == (r["decision"], r["pairs"]), "recorded decision differs")
    return dict(
        status="MEASURED_COLD_GATE_TRANSFER",
        decision=decision,
        scope="ONE_C110_GATE",
        family_sha256=family_sha,
        reference_sha256=REFERENCE,
        orders=orders,
        pairs=pairs,
        processes=life,
        memory_peak_B=r["memory_peak_B"],
        swap_peak_B=r["swap_peak_B"],
        commit=r["authority"]["commit"],
        tree=r["authority"]["tree"],
        sets=33,
        payload_B=ref["payload_B"],
        scratch_B=ref["scratch_B"],
        model_forwards=0,
        product_requests=0,
        integrated_energy_J=None,
    )


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
