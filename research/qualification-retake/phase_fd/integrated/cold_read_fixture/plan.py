"""Select the previously certified mandatory jobs; only traces and GGUF metadata are read."""

import argparse
import collections
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INT = HERE.parent
sys.path.insert(0, str(INT))
import analyse  # noqa: E402
import limits  # noqa: E402
import mandatory  # noqa: E402

FIXTURE = "c4228a842f5b97efd69da11b6c665a7bc6bdaa68b7d0381f5a7f28f19bf62de8"
LIMITS = "47476b0d8f0435c5e4c04f56a73edbb85f81e22ef9f9ba80a92c3b19b67d5b74"
INVENTORY = "2c8ca725f50000bf3177712cfa30d29a809f77f25826b425ea67d8fcbffd6d82"
GENERATION = "8f83497fe6b7d403232448b72e4f06a3d28eda1a7774ab87635fef040346f930"
ROLES = ("gate", "down", "up")
PAYLOAD = 4406400
MODEL_SIZE = 63387346208
MODEL_SHA = "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def pinned(path, digest):
    need(sha(path) == digest, "changed " + path.name)
    return json.loads(path.read_bytes())


def import_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def metadata(path):
    need(sha(path) == INVENTORY, "original GGUF inventory")
    data = [json.loads(line) for line in path.read_bytes().splitlines()]
    need(data[0]["tensor_count"] == len(data) - 1, "inventory cardinality")
    by_name = {r["name"]: r for r in data[1:]}
    need(len(by_name) == len(data) - 1, "tensor name collision")
    result = {}
    for layer in range(36):
        for role, tag in enumerate(ROLES):
            t = by_name[f"blk.{layer}.ffn_{tag}_exps.weight"]
            need(
                t["shape"] == [2880, 2880, 128]
                and t["tensor_type"] == "mxfp4"
                and t["n_bytes"] == 128 * PAYLOAD,
                "tensor geometry",
            )
            result[layer, role] = (t["data_offset"], PAYLOAD)
    return result


def selected_range(expert, base, size, offset, count, returned, limit):
    logical = base + expert * size
    aligned = logical // 4096 * 4096
    n = (logical - aligned + size + 4095) // 4096 * 4096
    need(
        0 <= expert < 128
        and size > 0
        and 0 <= aligned
        and aligned + n <= limit
        and (offset, count, returned) == (aligned, n, n),
        "DIO range or returned bytes",
    )
    return [logical, size, aligned, n]


def assemble(rows, meta, start, first, limit=MODEL_SIZE):
    """All own-wave membership tests use FIFO event order, never completion order."""
    sites = {}
    spans = {}
    resident = {(r.layer, r.expert) for r in rows if r.kind == 5 and r.a}
    seen = set(resident)
    releases = {}
    demands = {}
    queues = {}
    reads = collections.defaultdict(list)
    for index, r in enumerate(rows):
        site = (r.call, r.tile, r.layer, r.wave)
        key = (r.layer, r.expert, r.slot, r.gen)
        if r.kind == 9:
            need(site not in sites, "repeated wave")
            sites[site] = index
            spans[site] = [r.ns]
        elif r.kind == 23:
            spans[site].append(r.ns)
        elif r.kind == 11 and key in releases:
            raise ValueError("duplicate first generation")
        elif r.kind == 11 and (r.layer, r.expert) not in seen:
            seen.add((r.layer, r.expert))
            releases[key] = site
        elif key in releases:
            if r.kind == 10:
                demands.setdefault(key, site)
            elif r.kind == 12:
                queues.setdefault(key, (site, r.a, index))
            elif r.kind == 15:
                reads[key].append(r)
    groups = collections.defaultdict(list)
    for key, site in releases.items():
        if demands.get(key) != site or queues.get(key, (None,))[:2] != (site, 0):
            continue
        a, b = spans[site]
        # ±1 ms outer synchronization allowance; a crossing callback is free.
        if a < start + 1_000_000 or b > first - 1_000_000:
            continue
        items = reads[key]
        need(
            len(items) == 3
            and len({r.worker for r in items}) == 1
            and {r.component for r in items} == set(range(3))
            and all(a <= r.begin <= r.ns <= b for r in items)
            and all(x.ns <= y.begin for x, y in zip(items, items[1:], strict=False)),
            "serial service",
        )
        layer, expert, slot, generation = key
        ranges = [
            selected_range(expert, *meta[layer, r.component], r.a, r.b, r.c, limit) for r in items
        ]
        groups[site].append(
            (
                queues[key][2],
                sum(r.ns - r.begin for r in items),
                {
                    "expert": expert,
                    "slot": slot,
                    "generation": generation,
                    "ranges": ranges,
                    "components": [r.component for r in items],
                },
            )
        )
    plan = []
    floor = 0
    for site in sorted(groups, key=sites.__getitem__):
        ordered = sorted(groups[site], key=lambda g: g[0])
        floor += mandatory.lower_bound([x[1] for x in ordered])
        plan.append({"site": list(site), "experts": [x[2] for x in ordered]})
    return plan, floor


def make(a):
    need(
        sha(HERE / "protocol.md") == FIXTURE and sha(INT / "mandatory.py") == GENERATION,
        "frozen method",
    )
    ref = pinned(INT / "nominal-r01/limits.json", LIMITS)
    on = pinned(a.on_dir / "receipt.json", ref["sources"]["on"])
    off = pinned(a.off_dir / "receipt.json", ref["sources"]["off"])
    need(
        on["status"] == "PASS_C281_PFJ_ON"
        and off["status"] == "PASS_C281_PFJ_OFF"
        and on["trajectories"] == off["trajectories"]
        and on["gates"] == off["gates"],
        "qualified equivalent trajectories",
    )
    conv = import_module("selected_c281", INT / "conversation/profile.py")
    need(sha(INT / "limits.py") == ref["sources"]["code"], "clock method")
    for d, receipt in ((a.on_dir, on), (a.off_dir, off)):
        unit = receipt["unit"]
        need(Path(unit).name == unit, "monitor name")
        monitor = pinned(d / "raw" / (unit + ".json"), receipt["monitor_sha256"])
        need(monitor["returncode"] == 0 and receipt["model_launches"] == 1, "monitor cleanup")
    conv.samples.historic_manifest(a.historical)
    need(
        conv.trajectories(a.on_dir / "raw", on, a.historical) == on["trajectories"],
        "native output IDs",
    )
    archive = pinned(a.archive_manifest, ref["sources"]["private_raw_manifest"])
    # Manifest entries remain local under the original run name when the raw is relocated.
    raw_entry = "tesy-phase-fd-c281-on-20261125-r02/raw/T2-result.json"
    label = archive["files"][raw_entry]
    target = a.on_dir / "raw/T2-result.json"
    raw = pinned(target, label["sha256"])
    need(target.stat().st_size == label["bytes"], "T2 result length")
    journal = a.on_dir / "raw/events.pfj"
    rows, header = analyse.read_journal(journal)
    need(header["journal_sha256"] == on["journal_sha256"] == ref["sources"]["journal"], "journal")
    expected = pinned(a.on_dir / "journal-audit.json", on["journal_audit_sha256"])
    grade = analyse.audit(rows, header)
    # The captured FD and byte offsets are checked from the journal; do not open the GGUF.
    need(
        expected["fd_identity_checked"] is True
        and json.loads(json.dumps(grade)) == dict(expected, fd_identity_checked=False)
        and grade["status"] == "PASS",
        "journal audit",
    )
    clock = limits.joint_clock(rows, grade["calls"], raw, on["rows"][1])
    original = mandatory.evaluate(rows, raw, on["rows"][1], clock)
    need(original == ref["mandatory_service"], "mandatory witness")
    start = int(raw["request_started_monotonic"] * 10**9)
    first = start + int(raw["stream_metrics"]["first_final_content_chunk_s"] * 10**9)
    groups, floor = assemble(rows, metadata(a.inventory), start, first)
    counts = [len(g["experts"]) for g in groups]
    jobs = sum(counts)
    ranges = [r for g in groups for job in g["experts"] for r in job["ranges"]]
    aligned = sum(r[3] for r in ranges)
    logical = sum(r[1] for r in ranges)
    nmax = max(counts)
    need(
        jobs == original["required_jobs"]["first"] == 875
        and len(ranges) == 2625
        and floor == original["mandatory_floor_ns"]["first"] == 6231568365
        and logical == jobs * 3 * PAYLOAD
        and 2 * aligned <= 24 * 2**30,
        "selected jobs or bytes",
    )
    residual = original["fixed_outside_callbacks_ns"]["first"]
    need(residual == 5996895714, "callback complement")
    info = {
        "status": "PASS_AUTHENTICATED_FIRST_READ_PLAN",
        "model_sha256": MODEL_SHA,
        "model_size": MODEL_SIZE,
        "inventory_sha256": INVENTORY,
        "source_limits_sha256": LIMITS,
        "on_sha256": ref["sources"]["on"],
        "off_sha256": ref["sources"]["off"],
        "journal_sha256": header["journal_sha256"],
        "t2_result_sha256": label["sha256"],
        "plan_protocol_sha256": FIXTURE,
        "job_count": jobs,
        "component_count": len(ranges),
        "group_count": len(groups),
        "max_group_jobs": nmax,
        "group_size_histogram": dict(sorted(collections.Counter(counts).items())),
        "max_aligned_read_bytes": max(r[3] for r in ranges),
        "staging_bytes_conservative": nmax * 3 * max(r[3] for r in ranges),
        "aligned_bytes": aligned,
        "logical_bytes": logical,
        "original_service_floor_ns": floor,
        "fixed_outside_callbacks_ns": residual,
        "service_budget_ns": 10**10 - residual,
    }
    return info, groups


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in (
        "on-dir",
        "off-dir",
        "historical",
        "inventory",
        "archive-manifest",
        "new-output-dir",
    ):
        p.add_argument("--" + key, required=True, type=Path)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    try:
        info, groups = make(a)
        dest = out / "plan.json"
        dest.write_text(
            json.dumps(info | {"groups": groups}, sort_keys=True, separators=(",", ":")) + "\n"
        )
        receipt = info | {"plan_sha256": sha(dest), "plan_bytes": dest.stat().st_size}
    except (ValueError, KeyError, TypeError, OSError) as e:
        receipt = {"status": "FAIL_PRESERVED", "error_type": type(e).__name__}
        (out / "error.txt").write_text(str(e) + "\n")
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(receipt["status"], sha(out / "receipt.json"))
    return int(receipt["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
