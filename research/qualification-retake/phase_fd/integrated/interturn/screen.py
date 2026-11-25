"""Price a secondary cache filled after the T1 response, before T2's request clock."""

import argparse
import hashlib
import json
import struct
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROTOCOL = "e1a9e916e3cf0d773fd39089546f6250a3ad1cb2e6661f9d714f3dce82b11ac5"
HOST = "a3398265b4bf33ed75f4898b346c2d9a988865cd5ca9cf98668826b52d41f700"
CLIENT = "2cca03a7262a0715338ffd73e7ec3ca4d129dfa5f03760fe36971b51d46d31b9"
ARMS = {
    "OFF": (
        36,
        "tesy-phase-fd-c281-off-20261125-r01",
        "eac81d438a3aef8ed2e81789e14196ff791f80ac4d4ff57b957e0f528e3810bb",
    ),
    "ON": (
        37,
        "tesy-phase-fd-c281-on-20261125-r02",
        "4c7715c643684b4b7b058fb20d0daea19c95d766a0a60aad43ce2cb29d9c2239",
    ),
}
SIZE = 13_219_200
SPEED = 4_500_000_000
NS = 10**9
MARGIN = 1_000_000


def require(ok, why):
    if not ok:
        raise ValueError(why)


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def load(path, pin, length=None):
    data = path.read_bytes()
    require(len(data) < 256 * 1024 and hash_bytes(data) == pin, "artifact digest " + path.name)
    require(length is None or length == len(data), "archived length " + path.name)
    return json.loads(data, parse_float=Decimal)


def case(t1_end, t2_start, required, primary):
    require(0 < t1_end <= t2_start and 0 <= primary <= 199, "interturn order/primary grant")
    observed = (t2_start - t1_end) * NS
    upper = (
        int((t2_start * NS).to_integral_value(rounding=ROUND_CEILING))
        - int((t1_end * NS).to_integral_value(rounding=ROUND_FLOOR))
        + 2 * MARGIN
    )
    count, residue = divmod(upper * SPEED // NS, SIZE)
    n = max(0, required - primary)
    return {
        "gap_ns_nearest": int(observed.to_integral_value()),
        "upper_ns": upper,
        "max_bytes": upper * SPEED // NS,
        "max_complete_keys": count,
        "residual_bytes": residue,
        "required_after_primary_grant": n,
        "required_nvme_bytes": n * SIZE,
        "headroom_bytes": upper * SPEED // NS - n * SIZE,
        "minimum_ns_at_scenario_rate": (NS * n * SIZE + SPEED - 1) // SPEED,
        "decision": "HEADROOM_ONLY" if count >= n else "NO_GO_FIXED_WINDOW",
    }


def evaluate(archive):
    require(hash_bytes((HERE / "protocol.md").read_bytes()) == PROTOCOL, "protocol")
    require(
        hash_bytes((HERE.parents[4] / "tools/optin_integration_client.py").read_bytes()) == CLIENT,
        "client clock source",
    )
    host = load(HERE.parent / "host_cache/evidence/receipt.json", HOST)
    require(host["status"] == "PASS" and host["initial_resident_reloads"] == 199, "warm volume")
    result = dict(
        status="PASS_REPRODUCED_INTERTURN_WINDOWS",
        method_sha256=hash_bytes(Path(__file__).read_bytes()),
        protocol_sha256=PROTOCOL,
        host_cache_sha256=HOST,
        client_sha256=CLIENT,
        arms={},
        bandwidth_B_per_s=SPEED,
        payload_bytes=SIZE,
        endpoint_margin_ns=MARGIN,
    )
    for label, (part, name, manifest_sha) in ARMS.items():
        root = archive / f"part-{part:02d}"
        files = load(root / "manifest.json", manifest_sha)["files"]

        def member(file, name=name, files=files, root=root):
            key = f"{name}/{file}"
            item = files[key]
            return load(root / key, item["sha256"], item["bytes"]), item["sha256"]

        receipt, receipt_sha = member("receipt.json")
        require(
            receipt_sha == host[f"{label.lower()}_sha256"]
            and receipt["status"] == "PASS_C281_PFJ_" + label,
            "qualified arm",
        )
        measured = []
        digests = []
        for i, validated in enumerate(receipt["rows"], 1):
            row, row_sha = member(f"raw/T{i}-result.json")
            ids = row["official_ids"]
            require(
                0 < len(ids) <= 8192
                and all(type(k) is int and 0 <= k < 201088 for k in ids)
                and hash_bytes(struct.pack(f"<{len(ids)}i", *ids))
                == validated["official_ids_sha256"],
                "official input vector",
            )
            require(
                row["accepted"] is True
                and row["finish_reason"] == "stop"
                and row["prefix_gate"] == row["content_gate"] == "PASS"
                and row["usage"]["completion_tokens"]
                == validated["completion_n"]
                == (78, 47)[i - 1],
                "qualified completion",
            )
            start, end = (row["request_" + s + "_monotonic"] for s in ("started", "ended"))
            require(
                0 < start < end and abs(end - start - row["request_wall_s"]) < Decimal("1e-9"),
                "request clock closure",
            )
            measured.append((start, end))
            digests.append(row_sha)
        require(len(measured) == 2, "two requests")
        cells = {}
        for denom, gate in host["gates"].items():
            required = gate["minimum_warm_keys_for_compulsory_floor"]
            require(
                required in (167, 224) and gate["minimum_warm_payload_bytes"] == required * SIZE,
                "required warm payload",
            )
            cells[denom] = {
                "nvme_only": case(measured[0][1], measured[1][0], required, 0),
                "primary_199_granted": case(measured[0][1], measured[1][0], required, 199),
            }
        result["arms"][label] = dict(
            manifest_sha256=manifest_sha,
            receipt_sha256=receipt_sha,
            turn_result_sha256=digests,
            volume_required_from="journal_ON_R02",
            cells=cells,
        )
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive-root", required=True, type=Path)
    p.add_argument("--new-output-dir", required=True, type=Path)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = evaluate(a.archive_root)
    except (ValueError, KeyError, OSError, IndexError, TypeError) as e:
        result = {"status": "FAIL_PRESERVED", "error_type": type(e).__name__}
        (a.new_output_dir / "error.txt").write_text(str(e) + "\n")
    raw = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
    (a.new_output_dir / "receipt.json").write_bytes(raw)
    print(result["status"], hash_bytes(raw))
    raise SystemExit(result["status"] == "FAIL_PRESERVED")
