#!/usr/bin/env python3
"""Check C294 R0 decode reads and a mounted file's USB ceiling without reading weights."""

import argparse
import fcntl
import json
import os
import struct
import subprocess
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
C294 = "c294-feature-ready-service-window-20261006"
INDEX_SHA = "5a689ed0c3e7e328973a12de229c3a6ff4e151c14d568d49e517ff7dee98fd84"
CPP_SHA = "270ede951c3911c8acbd878600f7bab3692215b820d5853d67071b790297f9fc"
CLIENT_SHA = "dce6c8e7b172f705f65d70105bc563a945655d74c9504639b5c513a8b81f960e"
SIZE = 63_387_346_208
ROLE = 4_406_400


def require(ok, message):
    if not ok:
        raise ValueError(message)


def file_identity(st):
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def topology(model):
    # FS_IOC_FIEMAP, Linux x86_64. Zero flags requests metadata without FIEMAP_FLAG_SYNC.
    head, extent = struct.Struct("=QQIIII"), struct.Struct("=QQQQQIIII")
    cap = 1024
    buf = bytearray(head.size + cap * extent.size)
    head.pack_into(buf, 0, 0, 2**64 - 1, 0, 0, cap, 0)
    with model.open("rb", buffering=0) as stream:
        before = os.fstat(stream.fileno())
        require(before.st_size == SIZE, "wrong GGUF size")
        fcntl.ioctl(stream.fileno(), 0xC020660B, buf, True)
        mapped = head.unpack_from(buf)[3]
        require(0 < mapped <= cap, "unsupported extent count")
        end = 0
        for i in range(mapped):
            logical, _, size, _, _, flags, *_ = extent.unpack_from(buf, head.size + i * extent.size)
            require(
                size > 0 and logical == end and flags == int(i == mapped - 1),
                "hole, unwritten/unknown mapping or incomplete extent map",
            )
            end += size
        require(end >= SIZE, "incomplete coverage")
        mibps = []
        dev = Path("/sys/dev/block") / f"{os.major(before.st_dev)}:{os.minor(before.st_dev)}"
        disk = dev.resolve(strict=True)
        require(
            (disk / "partition").is_file() and not list((disk.parent / "slaves").iterdir()),
            "expected directly backed partition",
        )
        for ancestor in disk.parents:
            if (ancestor / "speed").is_file() and (ancestor / "rx_lanes").is_file():
                mibps.append(
                    {
                        "device": ancestor.name,
                        "megabits_s": int((ancestor / "speed").read_text()),
                        "rx_lanes": int((ancestor / "rx_lanes").read_text()),
                        "tx_lanes": int((ancestor / "tx_lanes").read_text()),
                    }
                )
        require(
            mibps and mibps[0]["rx_lanes"] == mibps[0]["tx_lanes"] == 1,
            "unidentified endpoint or multiple endpoint lanes",
        )
        require(
            file_identity(os.fstat(stream.fileno()))
            == file_identity(before)
            == file_identity(model.stat()),
            "file changed",
        )
    fs = subprocess.check_output(["findmnt", "-n", "-o", "FSTYPE", "-T", str(model)], text=True)
    require(set(fs.splitlines()) == {"ext4"}, "expected ext4")
    drivers = {(d / "driver").resolve().name for d in disk.parents if (d / "driver").exists()}
    require("uas" in drivers or "usb-storage" in drivers, "missing USB mass-storage driver")
    return {
        "filesystem": "ext4",
        "driver": "uas" if "uas" in drivers else "usb-storage",
        "partition": disk.name,
        "extent_count": mapped,
        "extent_bytes": end,
        "usb_endpoint_to_root": mibps,
        "wire_bits_s": min(x["megabits_s"] for x in mibps) * 10**6,
    }


def audit_arm(raw, paths, case, number, rate):
    arm = f"c294-{case}-{number}-on"
    input_hashes = {}

    def read(suffix):
        name = arm + suffix
        path = raw / name
        data = path.read_bytes()
        pin = paths["results/" + C294 + "/raw/" + name]
        digest = sha256(data).hexdigest()
        require((len(data), digest) == (pin["bytes"], pin["sha256"]), "raw digest/size differs")
        input_hashes[suffix] = digest
        return data

    native = json.loads(read(".native/result.json"))
    bounded = json.loads(read(".json"))
    stderr = read(".stderr")
    require(
        bounded["run_id"] == arm and bounded["returncode"] == 0 and not bounded["stop_reason"],
        "invalid run",
    )
    require(
        b"MoE expert streaming uses O_DIRECT (page cache bypassed)" in stderr
        and b"falling back to buffered streaming reads" not in stderr,
        "direct mode unverified",
    )
    require(
        (
            native["profile"],
            native["transport"],
            native["trace"],
            native["decode_calls"],
            len(native["teacher_forced_ids"]),
        )
        == ("R0", "ORIGINAL", True, 32, 32),
        "wrong profile/work",
    )
    rows = read(".native/events.tsv").decode().splitlines()
    require(
        rows[0].split() == "kind us call route layer expert slot gen component bytes rows".split()
        and len(rows) - 1 == native["trace_events"],
        "incompatible journal",
    )
    calls, jobs, demands = {}, defaultdict(list), defaultdict(set)
    for line in rows[1:]:
        kind, t, c, route, layer, expert, slot, gen, part, size, _ = map(int, line.split())
        if kind in (15, 16):
            require((kind, c) not in calls, "duplicate call endpoint")
            calls[kind, c] = t
        if c == 0:
            continue
        require(1 <= c <= 32, "wrong decode call")
        if kind == 3:
            demands[c, layer].add(expert)
        if kind in (5, 6, 7, 8, 9, 10):
            jobs[c, route, layer, expert, slot, gen].append((kind, part, size, t))
    require(set(calls) == {(k, c) for c in range(33) for k in (15, 16)}, "missing call boundary")
    require(
        all(calls[15, c] < calls[16, c] for c in range(33))
        and all(calls[16, c] <= calls[15, c + 1] for c in range(32)),
        "overlapping calls",
    )
    require(
        set(demands) == {(c, layer) for c in range(1, 33) for layer in range(36)}
        and all(len(ids) == 4 for ids in demands.values()),
        "routing coverage",
    )
    lifecycle = [(5, -1, 0), *((k, p, ROLE) for p in range(3) for k in (6, 7, 8, 9)), (10, -1, 0)]
    loads = Counter()
    for (c, _, layer, expert, _, _), records in jobs.items():
        require([r[:3] for r in records] == lifecycle, "incomplete generation")
        times = [r[3] for r in records]
        require(
            calls[15, c] <= times[0] and times[-1] <= calls[16, c] and times == sorted(times),
            "worker read crosses decode boundary",
        )
        require(expert in demands[c, layer], "non-authoritative load")
        loads[c] += 1
    total = sum(loads.values()) * 3 * ROLE
    per_step = total / 32
    wire = rate / 8
    return {
        "arm": arm,
        "decode_steps": 32,
        "generation_count": sum(loads.values()),
        "component_reads": 3 * sum(loads.values()),
        "mandatory_payload_bytes": total,
        "bytes_per_step": per_step,
        "wire_limit_steps_s": wire / per_step,
        "min_decode_wire_seconds": total / wire,
        "required_bytes_s_at_six": 6 * per_step,
        "minimum_payload_reduction_fraction_at_six": 1 - wire / (6 * per_step),
        "sha256": input_hashes,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--raw-dir", type=Path, required=True)
    ap.add_argument("--backend", type=Path, required=True)
    ap.add_argument("--new-output-dir", type=Path, required=True)
    args = ap.parse_args()
    args.new_output_dir.mkdir(exist_ok=False)
    try:
        index = (HERE / "results" / C294 / "raw-manifest.json").read_bytes()
        require(sha256(index).hexdigest() == INDEX_SHA, "raw index differs")
        require(
            sha256((args.backend / "src/llama-moe-stream.cpp").read_bytes()).hexdigest() == CPP_SHA,
            "unexpected backend reader",
        )
        require(
            sha256((HERE / "tools/expert_service_window.cpp").read_bytes()).hexdigest()
            == CLIENT_SHA,
            "unexpected phase definition",
        )
        paths = {row["path"]: row for row in json.loads(index)["files"]}
        link = topology(args.model)
        arms = [
            audit_arm(args.raw_dir, paths, case, i, link["wire_bits_s"])
            for case in ("nominal153", "code153")
            for i in (2, 3)
        ]
        result = {
            "scope": "CONDITIONAL_FORMAL_SAME_DIRECT_READS_ON_USB",
            "wire": link,
            "manifest_sha256": INDEX_SHA,
            "backend_sha256": CPP_SHA,
            "client_sha256": CLIENT_SHA,
            "arms": arms,
        }
    except Exception as exc:
        (args.new_output_dir / "FAIL.txt").write_text(type(exc).__name__ + "\n")
        raise
    tmp = args.new_output_dir / ".receipt.pending"
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.rename(args.new_output_dir / "receipt.json")


if __name__ == "__main__":
    main()
