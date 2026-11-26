"""Compare mutex-ordered PFJ1 primary descriptors at the first decode ENTER of C281 T2."""

import argparse
import hashlib
import importlib.util
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("decode_entry_audit", UNIT / "t1_capture/audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
fd, check, digest = audit.fd, audit.check, audit.digest
PROTOCOL = "72600793f1600369c7bbc60aaa4211135f2d1e8b5007ec0d9c090bd8a8417187"
ARMS = (
    (
        "part-37",
        "4c7715c643684b4b7b058fb20d0daea19c95d766a0a60aad43ce2cb29d9c2239",
        "tesy-phase-fd-c281-on-20261125-r02",
        "78c3a5bb34353d2b880b14bfa80634cd06dfe465beec529446206a8728af3f43",
        audit.PRIOR,
        1,
    ),
    (
        "part-40",
        "4907245d68f604c31918d48d50259a60476ef76c1bfc0f848d98db659606b513",
        "tesy-pfj-victims-on-20261125-r01",
        "fc368b04cc5ea6258c05594ab52306c336446f40ab06ea2ec5fe287eabfeef5d",
        "40d2ea8049ccee9213ffc3f317482d67ebbed85a887a933043a3f4e7bd132033",
        74,
    ),
)


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def active_workers(prefix):
    # The snapshot carries a claim bit but no initial worker ID. Only an actual
    # DISPATCH or worker activity on that inherited claim identifies its owner.
    active = {fd.identity(r): None for r in prefix if fd.NAMES[r.kind] == "SLOT" and r.b}
    for r in prefix:
        kind = fd.NAMES[r.kind]
        key = fd.identity(r)
        if kind == "DISPATCH":
            check(key not in active and r.worker not in active.values(), "active worker reused")
            active[key] = r.worker
        elif kind in ("READ", "SET", "PUBLISH"):
            check(key in active and active[key] in (None, r.worker), "worker without claim")
            if kind == "PUBLISH":
                del active[key]
            else:
                active[key] = r.worker
    return active


def before_decode(rows, header, start_call):
    grade = audit.conservation(rows, header, None, start_call)
    expected = [(5, [2044, 2048], [5]), (148, [2049, 2196], [32, 32, 32, 32, 20])]
    expected += [(1, [p, p], [1]) for p in range(2197, 2243)]
    calls = grade["calls"][start_call - 1 :]
    check([(c["tokens"], c["positions"], c["tiles"]) for c in calls] == expected, "T2 geometry")
    cut = next(i for i, r in enumerate(rows) if r.kind == 1 and r.call == start_call + 2)
    returned = next(i for i, r in enumerate(rows) if r.kind == 2 and r.call == start_call + 1)
    prefix = rows[:cut]
    slots, fifo, _ = audit.state_before(prefix)
    active = active_workers(prefix)
    claimed = {
        (index // 40, index % 40, generation, expert)
        for index, (expert, generation, _, claim) in enumerate(slots)
        if claim
    }
    check(set(active) == claimed, "claims versus in-flight workers")
    projections = audit.authority_projection(prefix, start_call)
    events = {
        fd.NAMES[kind]: [r for r in projections["host"] if r[0] == kind] for kind in (10, 11, 27)
    }
    events["PUBLISH"] = projections["publication"]
    r = rows[returned]
    meta = {
        "records": header["records"],
        "journal_sha256": header["journal_sha256"],
        "cut_record_index_zero_based": cut,
        "return_call": r.call,
        "decode_call": rows[cut].call,
        "return_queue": r.b,
        "return_claimed": r.c,
        "return_to_enter_ns": rows[cut].ns - r.ns,
        "between_return_enter_records": dict(
            Counter(fd.NAMES[e.kind] for e in rows[returned + 1 : cut])
        ),
    }
    return slots, fifo, active, events, meta


def layer_view(slots, fifo, active, layer):
    segment = slots[40 * layer : 40 * (layer + 1)]
    ready = sorted(expert for expert, _, state, _ in segment if state == 2)
    check(len(ready) == len(set(ready)), "duplicate resident")
    return {
        "ready_members": ready,
        "slot_expert": [s[0] for s in segment],
        "slot_generation": [s[1] for s in segment],
        "slot_state": [s[2] for s in segment],
        "slot_claim": [s[3] for s in segment],
        "fifo": [key for key in fifo if key[0] == layer],
        "active": sorted((key, worker) for key, worker in active.items() if key[0] == layer),
    }


def delta(a, b):
    # Membership counts keys in the symmetric difference. FIFO positions retain
    # duplicate/stale entries as well as layer-local order. Claims retain slot.
    differences = {"ready_members": len(set(a["ready_members"]) ^ set(b["ready_members"]))}
    for k in a.keys() - {"ready_members"}:
        differences[k] = sum(x != y for x, y in zip(a[k], b[k], strict=False)) + abs(
            len(a[k]) - len(b[k])
        )
    return differences


def occupancy(view):
    return {
        "ready": view["slot_state"].count(2),
        "loading": view["slot_state"].count(1),
        "empty": view["slot_state"].count(0),
        "claimed": sum(view["slot_claim"]),
        "queued": len(view["fifo"]),
        "active": len(view["active"]),
    }


def load(root, arm):
    part, manifest_sha, name, receipt_sha, journal_sha, start = arm
    part_dir = root / part
    manifest_path = part_dir / "manifest.json"
    check(sha(manifest_path) == manifest_sha, "archive seal")
    manifest = json.loads(manifest_path.read_bytes())["files"]
    for rel, pin in (("receipt.json", receipt_sha), ("raw/events.pfj", journal_sha)):
        path = part_dir / name / rel
        entry = manifest[f"{name}/{rel}"]
        check(path.stat().st_size == entry["bytes"] and entry["sha256"] == pin, "manifest member")
    receipt = part_dir / name / "receipt.json"
    check(sha(receipt) == receipt_sha, "capture receipt")
    rows, header = fd.read_journal(part_dir / name / "raw/events.pfj")
    check(header["journal_sha256"] == journal_sha, "journal seal")
    slots, fifo, active, events, meta = before_decode(rows, header, start)
    meta.update(receipt_sha256=receipt_sha, part=part, archive_manifest_sha256=manifest_sha)
    return [layer_view(slots, fifo, active, n) for n in range(36)], fifo, events, meta


def compare(root):
    check(sha(HERE / "protocol.md") == PROTOCOL, "prespecification")
    auditor_sha = sha(UNIT / "t1_capture/audit.py")
    check(
        auditor_sha == "8421320989e437594d4026d350269b07c3bb3c0c540a3d79f011a06534480089",
        "capture auditor",
    )
    a, a_fifo, a_events, a_info = load(root, ARMS[0])
    b, b_fifo, b_events, b_info = load(root, ARMS[1])
    events = {}
    for k in a_events:
        left, right = a_events[k], b_events[k]
        events[k] = {
            "counts": [len(left), len(right)],
            "ordered_equal": left == right,
            "multiset_equal": Counter(left) == Counter(right),
            "ordered_sha256": [digest(left), digest(right)],
        }
    check(all(events[k]["ordered_equal"] for k in ("RANKS", "DEMAND")), "different T2 workload")
    groups = defaultdict(list)
    for layer, (x, y) in enumerate(zip(a, b, strict=True)):
        summary = [occupancy(x), occupancy(y), delta(x, y)]
        groups[json.dumps(summary, sort_keys=True)].append(layer)
    fields = {}
    for k in a[0]:
        views = [[layer[k] for layer in arm] for arm in (a, b)]
        fields[k] = {
            "ordered_sha256": [digest(v) for v in views],
            "different_layers": [i for i in range(36) if views[0][i] != views[1][i]],
        }
    return {
        "classification": "TRACE_DERIVED",
        "decision": "COMMON_OBSERVED_FIELDS_ONLY"
        if a == b and a_fifo == b_fifo
        else "NO_COMMON_TABLE_FOR_DIFFERING_FIELDS",
        "protocol_sha256": PROTOCOL,
        "program_sha256": sha(Path(__file__)),
        "capture_auditor_sha256": auditor_sha,
        "conservation_auditor_sha256": audit.PIN,
        "arms": [a_info, b_info],
        "prefill_projections": events,
        "cut_fields": fields,
        "complete_fifo_order_equal": a_fifo == b_fifo,
        "complete_fifo_sha256": [digest(a_fifo), digest(b_fifo)],
        "layer_groups": [
            {"layers": layers, "occupancy_by_arm": summary[:2], "difference_counts": summary[2]}
            for key, layers in groups.items()
            for summary in [json.loads(key)]
        ],
        "parking_ids": "NOT_JOURNALED",
        "initial_policy_hotness_and_age": "NOT_JOURNALED",
        "new_forward_count": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    result = args.new_output_dir / "receipt.json"
    try:
        report = compare(args.archive_root)
    except (OSError, ValueError, KeyError, IndexError, StopIteration) as error:
        status = (
            "NOT_RUN_RAW_REQUIRED" if isinstance(error, FileNotFoundError) else "FAIL_PRESERVED"
        )
        result.write_text(json.dumps({"status": status, "failure": str(error)}) + "\n")
        raise
    temp = args.new_output_dir / "receipt.tmp"
    temp.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temp.rename(result)


if __name__ == "__main__":
    main()
