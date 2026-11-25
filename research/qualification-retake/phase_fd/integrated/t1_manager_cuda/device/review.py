"""Regrade the five closed GPU operators, their resource journals and the Part 53 archive."""

import argparse
import json
import math
import struct
import sys
from datetime import datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
device = run_path(str(HERE / "run.py"))
checker = device["checker"]
need, sha = device["need"], device["sha"]
sys.path.insert(0, str(HERE.parents[5] / "tools"))
import c118_start_inventory as c118  # noqa: E402

PART = "3beb53b8731ea7eb5dbbf491cdc8e2075898300c923df0e54104516fd58f9409"
SOURCE = "20d66fe68189cb44b6871089619a30c6850058e093dac77c4f28e981da366155"
FAMILY = "tesy-ordered-device-20261125-r03"
BUILD = "tesy-manager-cuda-build-20261125-r03"
WIDTH = 32
SLAB = 32 * 17


def read(path):
    return json.loads(path.read_bytes())


def lines(path):
    return [json.loads(x) for x in path.read_bytes().splitlines()]


def sealed(root, manifest):
    need(sha(manifest) == PART, "part 53 digest")
    m = read(manifest)
    need(
        m["schema"] == "tesy-private-raw-archive-v1" and m["part"] == "part-53", "archive identity"
    )
    for name, x in m["files"].items():
        # Verify the populated rings of both the archive and the requested source.
        for base in (
            {manifest.parent, root}
            if name.startswith((FAMILY + "/", BUILD + "/"))
            else {manifest.parent}
        ):
            f = base / name
            need(
                not f.is_symlink() and f.stat().st_size == x["bytes"] and sha(f) == x["sha256"],
                "archived bytes: " + name,
            )
    need(
        len(m["files"]) == 137 and sum(x["bytes"] for x in m["files"].values()) == 1281816,
        "archive counts",
    )


def project(slot, values):
    """Decode each real block from the witness bytes, then dot its full row in float64."""
    levels = (0, 0.5, 1, 1.5, 2, 3, 4, 6, 0, -0.5, -1, -1.5, -2, -3, -4, -6)
    need(len(slot) == SLAB and len(values) == WIDTH, "MXFP4 witness geometry")
    result = []
    for off in range(0, SLAB, 17):
        scale = 2.0 ** (slot[off] - 127)
        codes = slot[off + 1 : off + 17]
        decoded = [levels[c & 15] for c in codes] + [levels[c >> 4] for c in codes]
        result.append(scale * math.fsum(a * b for a, b in zip(decoded, values, strict=True)))
    return result


def independent_ffn(slots):
    need(len(slots) == 12 * SLAB, "all operand bytes")
    activation = [0.25] * WIDTH
    # Rank zero survives the known [1,0,0,0] mask. All twelve operands are also byte-checked.
    gate, down, up = (slots[i * 4 * SLAB : i * 4 * SLAB + SLAB] for i in range(3))
    g, u = project(gate, activation), project(up, activation)
    h = [
        (1 + min(7.0, max(-7.0, y))) * min(7.0, x) / (1 + math.exp(-1.702 * min(7.0, x)))
        for x, y in zip(g, u, strict=True)
    ]
    return project(down, h)


def monitors(root, arm, physical, s, policy):
    inv = read(root / (arm + "-inventory.json"))
    r = physical["unit"] + "-" + arm
    raw = root / "raw"
    i = raw / (r + ".start-inventory.jsonl")
    m = raw / (arm + ".monitor.jsonl")
    need(
        sha(m) == s["monitor_sha256"]
        and sha(i) == s["start_inventory_sha256"] == inv["sha256"]
        and Path(inv["path"]).parts[-2:] == i.parts[-2:],
        "monitor inputs",
    )
    inventory, service = lines(i), lines(m)
    kw = dict(
        policy=policy, cap_bytes=2**31, expected_power={"source": "AC", "profile": "performance"}
    )
    utc = [datetime.fromisoformat(x["utc"]) for x in service]
    c118.require_inventory(root, r, dict(inv, path=str(i)), **kw, now=utc[0])
    need(
        len(service) == s["service_samples"]
        and s["inventory_s"] == inv["duration_s"]
        and len(inventory) == s["inventory_samples"]
        and 0 < service[-1]["elapsed_s"] <= s["wall_s"] < 30,
        "process costs",
    )
    phases = [x["phase"] for x in service]
    # All five sealed processes saw their owner on the first query, with no periodic rows.
    need(
        phases == ["entry", "active", "finish", "after_exit"]
        and [x["stage"] for x in service] == [0, 1, 2, 3]
        and all(x["attempt"] == 1 for x in service)
        and s["owner_handoff_attempts"] == dict(E=1, A=1, F=1),
        "handoff coverage",
    )
    owners = [x["observation"]["gpu_owners"] for x in service]
    need(
        owners[0] == owners[-1] == []
        and len(owners[1]) == 1
        and owners[1] == owners[2]
        and type(owners[1][0]) is int
        and owners[1][0] > 0,
        "GPU ownership",
    )
    t = [0] + [x["elapsed_s"] for x in service]
    need(
        all(0 < b - a <= 5 for a, b in zip(t, t[1:], strict=False))
        and all(0 < (b - a).total_seconds() <= 5 for a, b in zip(utc, utc[1:], strict=False)),
        "service monitor gaps",
    )
    for row in service:
        obs = row["observation"]
        c118.validate_sample(obs, **kw)
        need(
            obs["gpu"]["bdf"] == policy["gpu"]["bdf"]
            and obs["gpu"]["used_mib"] < 1536
            and 0 < row["peak_bytes"] <= physical["peak_bytes"] < 1856 * (2**20),
            "scope and local GPU cap",
        )
        need(
            obs["thermal"]["cpu_tctl_c"] < policy["cpu"]["warning_c"]
            and obs["gpu"]["temperature_c"] < policy["gpu"]["warning_c"]
            and all(
                v["warning_c"] is None
                or obs["thermal"]["nvme_composite_by_sensor"][v["sensor"]] < v["warning_c"]
                for v in policy["nvme"]
            ),
            "temperature guard",
        )
    ob = [x["observation"] for x in inventory + service]
    met = dict(
        inventory_s=inv["duration_s"],
        inventory_samples=len(inventory),
        service_samples=len(service),
        gpu_owner_counts=[len(x) for x in owners],
        gpu_used_mib=[x["observation"]["gpu"]["used_mib"] for x in service],
        cpu_max_c=max(x["thermal"]["cpu_tctl_c"] for x in ob),
        gpu_max_c=max(x["gpu"]["temperature_c"] for x in ob),
        nvme_max_c=max(max(x["thermal"]["nvme_composite_by_sensor"].values()) for x in ob),
        min_available_bytes=min(x["mem_available_bytes"] for x in ob),
        scope_peak_at_exit=service[-1]["peak_bytes"],
        child_wall_s=s["wall_s"],
    )
    return met, owners[1][0], datetime.fromisoformat(inventory[0]["utc"]), utc[-1]


def review(a):
    sealed(a.runs_root, a.manifest)
    b = a.runs_root / BUILD
    root = a.runs_root / FAMILY
    p = read(root / "receipt.json")
    build = read(b / "receipt.json")
    need(
        sha(root / "receipt.json") == SOURCE
        and sha(b / "receipt.json") == p["build_sha256"]
        and build["source_sha256"] == sha(b / "device.cpp")
        and build["tree"] == p["tree"]
        and build["commit"] == p["commit"]
        and build["status"] == "PASS_DEVICE_BUILD_ONLY"
        and p["model_forwards"] == 0
        and p["scope_cap"] == 2**31
        and build["protocol_sha256"] == p["protocol_sha256"]
        and sha(HERE / "protocol.md") == p["protocol_sha256"],
        "frozen inputs",
    )
    gate = read(a.c55)
    policy_file = a.c55.with_name("resource-policy.json")
    need(
        sha(a.c55) == p["c55_sha256"]
        and gate["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not gate["reason"]
        and sha(policy_file) == gate["canonical_policy_sha256"],
        "C55 policy",
    )
    policy = read(policy_file)
    need(
        read(HERE.parent.parent / "t1_native_sink/evidence/receipt.json")["monitor_provider"]
        == p["provider"],
        "NVML provider",
    )
    paths, _ = device["builder"]["providers"](a.map)
    arms, refs, pids, intervals = {}, {}, set(), []
    cpu = read(HERE.parent / "evidence/cpu.json")
    for k in ("old", "new"):
        refs[k] = independent_ffn((root / k / "slots.mxfp4").read_bytes())
    old, new = ((root / x / "out.f32").read_bytes() for x in ("old", "new"))
    for arm in checker["ARMS"]:
        d = root / arm
        s = p["arms"][arm]
        stdout = root / "raw" / (arm + ".stdout")
        need(
            sha(stdout) == s["stdout_sha256"] and device["verify_maps"](d, paths) == s["providers"],
            "native witnesses",
        )
        output = (d / "out.f32").read_bytes()
        witness = checker["verify_arm"](
            arm,
            (d / "slots.mxfp4").read_bytes(),
            device["builder"]["cpu"]["load_optional"](d / "bank.mxfp4"),
            output,
            device["builder"]["cpu"]["load_optional"](d / "token.f32"),
            device["parse"](stdout, arm, paths),
            old,
            new,
        )
        need(all(s[k] == v for k, v in witness.items()), "runner and witness agreement")
        generation = "new" if arm in ("new", "broken") else "old"
        observed = struct.unpack("<32f", output)
        errors = [abs(v - w) for v, w in zip(observed, refs[generation], strict=True)]
        need(all(math.isfinite(x) and x <= 1e-4 for x in errors), "independent decoded FFN")
        met, pid, start, stop = monitors(root, arm, p, s, policy)
        pids.add(pid)
        intervals.append((start, stop))
        arms[arm] = dict(
            **witness,
            decoded_operand_max_abs_err=max(errors),
            resources=met,
            also_equals_cpu_bits=witness["complete_output_sha256"]
            == cpu["arms"][arm]["complete_output_sha256"],
            mapped_objects={
                k: len((d / (k + ".providers")).read_text().splitlines()) for k in s["providers"]
            },
        )
    need(
        len(pids) == 5
        and all(
            stop < start for (_, stop), (start, _) in zip(intervals, intervals[1:], strict=False)
        ),
        "distinct sequential processes",
    )
    need(p["status"] == "PASS_CUDA_WAVE_FIXTURE_ONLY", "decision")
    return dict(
        status=p["status"],
        arms=arms,
        physical_sha256=SOURCE,
        archive_sha256=PART,
        build_sha256=p["build_sha256"],
        peak_scope_bytes=p["peak_bytes"],
        model_forwards=0,
        scalar_limit=1e-4,
        capture_bytes_per_case=3 * SLAB,
        final_primary_bytes_per_case=12 * SLAB,
        observed_family_s=(intervals[-1][1] - intervals[0][0]).total_seconds(),
        inventory_s=sum(x["resources"]["inventory_s"] for x in arms.values()),
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for k in ("runs-root", "manifest", "c55", "map", "new-output-dir"):
        ap.add_argument("--" + k, type=Path, required=True)
    a = ap.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        r = review(a)
    except (OSError, KeyError, ValueError, TypeError, RuntimeError) as exc:
        r = dict(status="FAIL_REVIEW", reason=f"{type(exc).__name__}: {exc}")
    device["save"](a.new_output_dir / "receipt.json", r)
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_REVIEW")


if __name__ == "__main__":
    raise SystemExit(main())
