"""Reopen build, marker and three native outputs without running a worker."""

import argparse
import hashlib
import json
from pathlib import Path

RAW = "9ec243ad8233ad169a63f36b920969822ea9805e074cd4d92f9169caea5c39bf"


def check(value, reason):
    if not value:
        raise ValueError(reason)


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def audit(rows):
    off, on, stale = (rows[m] for m in ("OFF", "ON", "STALE"))
    check(all(row["manager_destroyed"] and row["workers"] == 4 for row in rows.values()), "drain")
    check(
        off["proposal"] == on["proposal"] == list(range(4))
        and off["initial"] == on["initial"]
        and off["primary"] == on["primary"],
        "paired inputs or pool at return",
    )
    prim = off["primary"]
    check(len(prim) == 6 and all(len(a) == 40 for a in prim[:4]), "40-slot pool")
    check(len(set(prim[0]) - {-1}) == 4 and set(prim[0]) == {-1, 0, 1, 3, 4}, "admitted victims")
    used = [prim[0].index(e) for e in [0, 1, 3, 4]]
    check(off["routed_slots"] == on["routed_slots"] == used * 32, "authoritative returned slots")
    check(all(prim[1][s] == 1 and prim[2][s] == 2 and prim[3][s] == 0 for s in used), "generation")
    out = {}
    for row, wanted, speculative in [
        (off, [1, 1, 0, 1, 1], [0, 0, 0, 0, 0]),
        (on, [0, 0, 0, 1, 1], [1, 1, 1, 0, 0]),
    ]:
        primary = row["issued_primary_reads"]
        offered = row["issued_spec_reads"]
        check(primary == wanted and offered == speculative, "read per identity")
        n = row["window"]
        check(
            n == 12288
            and row["slab"] == 4096
            and row["sets"] == 12
            and 1 <= row["peak_reads"] <= 4,
            "transfer size, copies or concurrency",
        )
        out[row["mode"]] = dict(
            primary_reads=sum(primary),
            speculative_reads=sum(offered),
            pread_bytes=(sum(primary) + sum(offered)) * n,
            sets=row["sets"],
            set_bytes=row["sets"] * row["slab"],
            peak_reads=row["peak_reads"],
        )
    check(
        (on["delivered"], on["attached_before_ready"], on["running_waste_drained"]) == (2, 1, 1),
        "required race ordering",
    )
    check(
        stale["status"] == "PASS_STALE_OWNER_REJECTED"
        and stale["stale_sets"] == 0
        and stale["new_claim_preserved"]
        and stale["new_generation"] == 2
        and stale["idle"],
        "invalid generation modified the replacement",
    )
    return out


def review(src):
    receipt = src / "receipt.json"
    check(digest(receipt) == RAW, "frozen raw receipt")
    r = json.loads(receipt.read_bytes())
    check(
        r["model_forwards"] == 0 and r["status"] == "PASS_PREFILL_PACKED_DELIVERY_FIXTURE",
        "native family",
    )
    rows = {m: json.loads((src / (m + ".stdout")).read_bytes()) for m in ("OFF", "ON", "STALE")}
    check(rows == r["arms"] and digest(src / "fixture") == r["binary_sha256"], "raw outputs or ELF")
    marker = b"".join(
        b"".join(
            bytes((1 + 13 * e + 29 * k + i % 113) % 256 for i in range(4096)) for k in range(3)
        )
        + bytes([222]) * 4096
        for e in range(5)
    )
    check(
        (src / "marker.pack").read_bytes() == marker
        and digest(src / "marker.pack") == r["pack_sha256"],
        "original independent marker",
    )
    scope = r["final_scope"]
    check(
        scope["sole_process"]
        and scope["memory.peak"] <= scope["memory.max"] == 1 << 30
        and scope["memory.swap.current"] == scope["memory.swap.max"] == 0,
        "cgroup",
    )
    return dict(
        status="REPRODUCED_PACKED_PREFILL_DELIVERY",
        raw_sha256=RAW,
        commit=r["commit"],
        tree=r["tree"],
        pins=r["pins"],
        binary_sha256=r["binary_sha256"],
        marker_sha256=r["pack_sha256"],
        observed=audit(rows),
        elapsed_s=r["elapsed_s"],
        peak_memory=scope["memory.peak"],
        swap=0,
        model_forwards=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw", required=True, type=Path)
    p.add_argument("--new-output-dir", required=True, type=Path)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = review(a.raw)
    except Exception as e:
        (a.new_output_dir / "FAIL.json").write_text(json.dumps({"error": repr(e)}) + "\n")
        raise
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2)
        f.write("\n")
