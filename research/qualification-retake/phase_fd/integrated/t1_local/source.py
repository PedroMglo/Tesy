"""Attribute a completed nominal turn to its own sealed prefix, clock and process."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
INT = HERE.parent
PART = "4907245d68f604c31918d48d50259a60476ef76c1bfc0f848d98db659606b513"
FAIL = "fc368b04cc5ea6258c05594ab52306c336446f40ab06ea2ec5fe287eabfeef5d"
METHOD = "b8cf36ef997bf5a32bb0f2cb3d5eaa649cc71c14eede256edf8062217f05e5e9"
ARM = "tesy-pfj-victims-on-20261125-r01"
DSO = "911b3be5b529d8e07409c12cf600ca9f7f6182f7a397fc6de265e5ea4be254eb"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


audit = module("local_victim_audit", INT / "t1_capture/audit.py")
admit = module("local_victim_votes", INT / "t1_admission/screen.py")
possible = module("local_victim_opportunity", INT / "t1_opportunity/screen.py")
fd, need, pinned, sha = audit.fd, audit.check, possible.pinned, possible.sha


def manifest(part):
    m = pinned(part / "manifest.json", PART)
    need(m["part"] == "part-40" and len(m["files"]) == 35, "archive identity")
    return m["files"]


def prepared(part):
    # Read only the identified T1 segment from the journal in this process.
    files = manifest(part)
    root = part / ARM
    seal = pinned(root / "before-t2.json", files[ARM + "/before-t2.json"]["sha256"])
    candidates = pinned(root / "before-t2-candidates.json", seal["candidate_file_sha256"])
    with (root / "raw/events.pfj").open("rb") as f:
        f.seek(fd.HEADER.size)
        data = f.read(seal["bytes"])
    need(
        0 < seal["records"] < 262144
        and len(data) == seal["bytes"] == seal["records"] * fd.RECORD.size
        and hashlib.sha256(data).hexdigest() == seal["sha256"],
        "T1 pre-POST seal",
    )
    rows = [fd.Row(*x) for x in fd.RECORD.iter_unpack(data)]
    prefix, available = possible.opportunities(rows)
    votes = admit.select(rows)
    need(
        prefix == candidates
        and prefix["t1_calls"] == 73
        and votes["banks"]["recency"]["ordered_keys_sha256"]
        == prefix["capacities"]["353"]["ordered_keys_sha256"],
        "T1 selection",
    )
    return {"prefix": prefix, "available": available, "votes": votes}


def local_slots(prefix, descriptors):
    initial = {(r.layer, r.slot): r for r in prefix if r.kind == 5}
    order = [(layer, slot) for layer in range(36) for slot in range(40)]
    need(set(initial) == set(order) and len(descriptors) == len(order), "all primary slots")
    output = []
    for site, (expert, generation, state, claim) in zip(order, descriptors, strict=True):
        need(state in (0, 2) and not claim, "undrained primary")
        # A boundary descriptor has no event-time role in the price or FIFO replay.
        output.append(initial[site]._replace(expert=expert, gen=generation, a=state, b=claim))
    return output


def load_inputs(part, model, inventory, prepared_dir):
    files = manifest(part)
    for name, meta in files.items():
        path = part / name
        need(
            path.is_file()
            and not path.is_symlink()
            and path.stat().st_size == meta["bytes"]
            and sha(path) == meta["sha256"],
            "archive member " + name,
        )
    root = part / ARM
    r = pinned(root / "receipt.json", FAIL)
    selected = json.loads((prepared_dir / "selection.json").read_bytes())
    need(selected == json.loads(json.dumps(prepared(part))), "selection escrow")
    need(
        r["commit"] == "b6023112fab7f4f1f1d3e9f36e54e441293eedcb"
        and r["status"] == "FAIL_PRESERVED"
        and r["failure"] == "ValueError: T2 host route/order/binding"
        and r["model_launches"] == 1
        and r["cleanup"] == "SERVER_EXIT_0_OWNER_STOP_UNIT_CLOSED_PORT_AVAILABLE"
        and r["runtime_authority"]["status"] == "PASS_LIVE_AND_LOADER_C281",
        "closed physical session",
    )
    unit = r["unit"]
    raw = root / "raw"
    mon = pinned(raw / (unit + ".json"), r["monitor_sha256"])
    inv = json.loads((raw / (unit + ".start-inventory.receipt.json")).read_bytes())
    c55 = pinned(
        part.parent / "part-39/tesy-t1-victim-c55-20261125-r02/receipt.json",
        "8e6d043bfd5702367fcffdd20a2eddc7cbbf549bb6d05808042c725254f54680",
    )
    need(
        c55["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not c55["reason"]
        and c55["canonical_policy_sha256"] == sha(root / "resource-policy.json")
        and inv["cap_bytes"] == 20 * 2**30
        and inv["sample_count"] >= 60
        and inv["duration_s"] >= 60
        and inv["run_id"] == unit
        and inv["sha256"] == r["start_inventory"] == sha(raw / (unit + ".start-inventory.jsonl")),
        "C55/C118 admission",
    )
    loader = pinned(root / "qualified-loader.json", r["runtime_authority"]["loader_audit_sha256"])
    client = json.loads((root / "client-receipt.json").read_bytes())
    launch = pinned(raw / (unit + ".launch.json"), client["launch_sha256"])
    need(
        mon["returncode"] == 0
        and mon["stop_reason"] is None
        and mon["process_identity"] == launch["process_identity"] == client["process_identity"]
        and r["maxima"]["swap_bytes"] == 0
        and DSO in loader["initialized_sha256"].values()
        and client["status"] == "CLIENT_TWO_REQUESTS_PASS"
        and client["failure"] is None,
        "process identity, numeric library, resources and client",
    )
    official = json.loads(
        (INT / "../../history_lookup/native_ids/evidence/verified.json").read_bytes()
    )
    for n, (row, ref, trajectory) in enumerate(
        zip(r["rows"], official["turns"], r["trajectories"], strict=True), 1
    ):
        leg = json.loads((raw / f"T{n}-result.json").read_bytes())
        need(
            leg == client["rows"][n - 1]
            and leg["accepted"]
            and leg["finish_reason"] == "stop"
            and leg["prefix_gate"] == leg["content_gate"] == "PASS"
            and row["official_ids_sha256"] == ref["official_ids_sha256"]
            and trajectory["sampled_ids_sha256"] == ref["sampled_ids_sha256"],
            "natural trajectory",
        )
    seal = json.loads((root / "before-t2.json").read_bytes())
    full, header = fd.read_journal(raw / "events.pfj")
    cut, shift = seal["records"], selected["prefix"]["t1_calls"]
    descriptors, queue, _ = audit.state_before(full[:cut])
    need(not queue and full[cut].kind == 1 and full[cut].call == shift + 1, "T2 boundary")
    after = audit.conservation(full, header, model, shift + 1)
    expect = [(5, [2044, 2048], [5]), (148, [2049, 2196], [32, 32, 32, 32, 20])]
    expect += [(1, [p, p], [1]) for p in range(2197, 2243)]
    need(
        [(c["tokens"], c["positions"], c["tiles"]) for c in after["calls"][shift:]] == expect
        and after["fd_identity_checked"],
        "local T2 conservation, position or model inode",
    )
    tail = local_slots(full[:cut], descriptors) + [
        r._replace(call=r.call - shift if r.call > 0 else r.call) for r in full[cut:]
    ]
    now = client["rows"][1]
    need(
        full[cut].begin >= int(now["request_started_monotonic"] * 1e9)
        and r["rows"][1]["cache_n"] == 2044
        and r["rows"][1]["prompt_n"] == 153,
        "T2 POST and prefix",
    )
    return SimpleNamespace(
        rows=tail,
        summary=r["rows"][1],
        client=now,
        meta=admit.t2.planner.metadata(inventory),
        memory=admit.t2.host.STOP - r["maxima"]["cgroup_peak_bytes"],
        prefix=selected["prefix"],
        available=selected["available"],
        votes=selected["votes"],
        conservation=after["event_counts"],
        inventory_sha256=r["start_inventory"],
        inventory_samples=inv["sample_count"],
        journal=header["journal_sha256"],
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=("seal", "score"))
    for name in ("part", "model", "inventory", "prepared-dir", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=name in ("part", "new-output-dir"))
    p.add_argument("--prepared-sha256")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir(mode=0o700)
    try:
        need(sha(HERE / "protocol.md") == METHOD, "method")
        if a.phase == "seal":
            selection = prepared(a.part)
            possible.save(out / "selection.json", selection)
            result = {"status": "PASS_PREFIX_ONLY", "selection_sha256": sha(out / "selection.json")}
        else:
            prep = pinned(a.prepared_dir / "receipt.json", a.prepared_sha256)
            need(
                prep["status"] == "PASS_PREFIX_ONLY"
                and sha(a.prepared_dir / "selection.json") == prep["selection_sha256"],
                "T1 preparation",
            )
            inputs = load_inputs(a.part, a.model, a.inventory, a.prepared_dir)
            evaluate = module("t1_local_pricing", HERE / "evaluate.py")
            result = dict(
                status="PASS_SINGLE_SESSION_DIAGNOSTIC",
                capture_status="FAIL_PRESERVED",
                journal_sha256=inputs.journal,
                prepared_sha256=a.prepared_sha256,
                conservation=inputs.conservation,
                pricing_sha256=sha(HERE / "evaluate.py"),
                results=evaluate.evaluate(inputs),
            )
    except Exception as error:
        result = {"status": "FAIL_PRESERVED", "error": f"{type(error).__name__}: {error}"}
    result.update(source_sha256=sha(Path(__file__)), protocol_sha256=METHOD, archive_manifest=PART)
    possible.save(out / "receipt.json", result)
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
