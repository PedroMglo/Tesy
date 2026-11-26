"""Estimate host-to-GPU payload on the recorded routes at the measured stock slot count."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from cache_bound import (  # noqa: E402
    CAMPAIGN,
    EXPERT_BYTES,
    MANIFEST,
    MANIFEST_SHA,
    RATE,
    STEPS,
    minimum,
    read_arm,
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def link(device):
    path = device.resolve(strict=True)
    if [(path / field).read_text().strip() for field in ("vendor", "device")] != [
        "0x10de",
        "0x28a0",
    ]:
        raise ValueError("expected the 4060 laptop PCI device")
    chain = []
    for parent in (path, *path.parents):
        if not re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]", parent.name):
            continue
        rate = (parent / "max_link_speed").read_text().strip().split()
        if len(rate) != 3 or rate[1:] != ["GT/s", "PCIe"]:
            raise ValueError("unsupported PCI link capability")
        chain.append(
            {
                "device": parent.name,
                "max_gt_s": float(rate[0]),
                "lanes": int((parent / "max_link_width").read_text()),
            }
        )
    if len(chain) < 2 or not all(row["lanes"] > 0 and row["max_gt_s"] > 0 for row in chain):
        raise ValueError("incomplete PCI capability chain")
    return chain


def audit(raw, device):
    chain = link(device)
    ceiling = min(row["max_gt_s"] * 1e9 * row["lanes"] / 8 for row in chain)
    marker_data = (HERE.parent / "stock_log/startup-r1/markers.json").read_bytes()
    planner_data = (HERE.parent / "stock_cache_evidence/receipt.json").read_bytes()
    if json.loads(marker_data)["ubatch_le_8"]["payload_per_expert_bytes"] != EXPERT_BYTES:
        raise ValueError("stock payload differs")
    slots = json.loads(planner_data)["usable_shared_slots"]
    manifest = MANIFEST.read_bytes()
    if slots != 161 or sha(manifest) != MANIFEST_SHA:
        raise ValueError("slot count or manifest changed")
    entries = {entry["path"]: entry for entry in json.loads(manifest)["files"]}
    arms = {}
    for case in ("nominal153", "code153"):
        for n in (2, 3):
            name = f"c294-{case}-{n}-on.native"
            rel = Path(name) / "events.tsv"
            expected = entries[str(Path("results") / CAMPAIGN / "raw" / rel)]
            groups, _ = read_arm(raw / rel, expected)
            counts = {
                "free_initial_oracle": minimum(groups, slots),
                "every_demand_misses": sum(map(len, groups)),
            }
            estimates = {}
            for state, loads in counts.items():
                payload = loads * EXPERT_BYTES
                per_second = payload * RATE / STEPS
                estimates[state] = {
                    "loads": loads,
                    "payload_B": payload,
                    "required_B_s": per_second,
                    "gross_fraction": per_second / ceiling,
                }
            arms[name] = {"events": expected, "groups": len(groups), "scenarios": estimates}
    return {
        "protocol_sha256": sha((HERE / "protocol.md").read_bytes()),
        "steps_per_arm": STEPS,
        "steps_s": RATE,
        "c294_manifest_sha256": MANIFEST_SHA,
        "stock_marker_sha256": sha(marker_data),
        "planner_receipt_sha256": sha(planner_data),
        "pci": chain,
        "gross_max_B_s": ceiling,
        "shared_slots": slots,
        "scope": "CONDITIONAL_R0_ROUTES_STOCK_H2D_PAYLOAD",
        "arms": arms,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-dir", required=True, type=Path)
    p.add_argument("--device", type=Path, default=Path("/sys/bus/pci/devices/0000:c4:00.0"))
    p.add_argument("--new-output-dir", type=Path, required=True)
    args = p.parse_args()
    args.new_output_dir.mkdir(exist_ok=False)
    try:
        result = audit(args.raw_dir, args.device)
    except Exception as exc:
        (args.new_output_dir / "FAIL.txt").write_text(str(exc) + "\n")
        raise
    pending = args.new_output_dir / ".pending"
    pending.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n")
    pending.rename(args.new_output_dir / "receipt.json")
