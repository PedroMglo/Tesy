"""Component-origin oracle for the C135 single-placement ABBA receipts."""

import argparse
import hashlib
import json
import os
import resource
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PUBLIC_RECEIPT = "evidence-20261124-r1/io.json"
PINS = {
    "io_pair/plan.json": "0602cda61a6c16795c1efa883ebabee0f28848ff49c202e3221fbabc6d29cc0e",
    "io_pair/run.py": "877114b0623bd2adae0bfc59db5ab146c6c6299b1d95e2d13bfe957903d5b813",
    PUBLIC_RECEIPT: "d98ab5f5ff745b85076d2cd2a918a0c64e3cbccf05d1bc89732d81101ef238f2",
}
PROTOCOL = "727d18bcf092eedb19a9cd6baa1c50c0cbae72c504f7a6b67c7b78b0ecfac39c"
ARM_NAMES = ("arm-1-usb.json", "arm-2-nvme.json", "arm-3-nvme.json", "arm-4-usb.json")
COMPONENTS = ("gate", "down", "up")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def authenticated(path, sha, size=None):
    limit = 524288
    with path.open("rb") as source:
        actual = os.fstat(source.fileno()).st_size
        require(0 < actual <= limit and (size is None or actual == size), f"size: {path.name}")
        data = source.read(actual + 1)
    require(len(data) == actual and digest(data) == sha, f"digest: {path.name}")
    return data


def validate_plan(plan):
    groups = plan["groups"]
    require(
        (plan["call"], plan["position"], plan["component_order"]) == (3, 2197, list(COMPONENTS)),
        "C135 geometry",
    )
    require(
        [len(g["experts"]) for g in groups].count(1) == 14
        and sorted(len(g["experts"]) for g in groups) == [1] * 14 + [2, 4],
        "group shape",
    )
    for field in ("layer", "wait_end_us"):
        ordered = [g[field] for g in groups]
        require(ordered == sorted(set(ordered)), "group order")
    logical = aligned = jobs = 0
    for group in groups:
        experts = group["experts"]
        for key in ("expert", "slot"):
            require(len({e[key] for e in experts}) == len(experts), "duplicate job")
        for expert in experts:
            jobs += 1
            require(
                0 <= expert["expert"] < 128
                and 0 <= expert["slot"] < 40
                and expert["generation"] > 0,
                "job identity",
            )
            require(len(expert["ranges"]) == 3, "component count")
            for offset, size, start, count in expert["ranges"]:
                require(
                    size == 4406400
                    and start >= 0
                    and start % 4096 == 0
                    and 0 <= offset - start < 4096,
                    "range/alignment",
                )
                require(count == (offset - start + size + 4095) // 4096 * 4096, "request length")
                logical += size
                aligned += count
    require(
        (jobs, logical, aligned) == (plan["loads"], plan["logical_bytes"], plan["aligned_bytes"]),
        "plan totals",
    )


def validate_arm(plan, arm, transport, payloads):
    require(arm["status"] == "PASS" and arm["transport"] == transport, "arm identity")
    require(arm["payload_sha256"] == payloads, "payload order")
    require(
        (arm["logical_bytes"], arm["requested_bytes"])
        == (plan["logical_bytes"], plan["aligned_bytes"]),
        "arm bytes",
    )
    elapsed = 0
    for group, row in zip(plan["groups"], arm["groups"], strict=True):
        ds = row["pread_duration_ns"]
        require(
            row["layer"] == group["layer"] and len(ds) == 3 * len(group["experts"]),
            "duration identity",
        )
        require(all(type(d) is int and d > 0 for d in ds), "duration ns")
        require(sum(ds) == row["pread_sum_ns"], "worker time")
        critical = max(sum(ds[i : i + 3]) for i in range(0, len(ds), 3))
        require(
            critical <= row["pread_union_ns"] <= min(row["elapsed_ns"], sum(ds)),
            "union and elapsed",
        )
        elapsed += row["elapsed_ns"]
    require(elapsed == arm["service_ns"] <= arm["arm_wall_ns"], "service clock")


def group_oracle(group, usb, nvme):
    jobs = []
    bytes_by_origin = {
        origin: {"logical": 0, "requested": 0, "calls": 0} for origin in ("usb", "nvme")
    }
    for i, expert in enumerate(group["experts"]):
        u = usb[3 * i : 3 * i + 3]
        n = nvme[3 * i : 3 * i + 3]
        origins = []
        for a, b, (_offset, length, _start, size) in zip(u, n, expert["ranges"], strict=True):
            origin = "usb" if a < b else "nvme"
            origins.append(origin)
            counts = bytes_by_origin[origin]
            counts["calls"] += 1
            counts["logical"] += length
            counts["requested"] += size
        jobs.append(
            {
                "expert": expert["expert"],
                "slot": expert["slot"],
                "generation": expert["generation"],
                "origin": origins,
                "usb_ns": sum(u),
                "nvme_ns": sum(n),
                "mixed_ns": sum(min(a, b) for a, b in zip(u, n, strict=True)),
            }
        )
    clocks = {k: max(j[k] for j in jobs) for k in ("usb_ns", "nvme_ns", "mixed_ns")}
    for i, job in enumerate(jobs):
        # Revert this choice only, holding all other choices at their optimum.
        job["usb_components_whose_reversion_delays_barrier"] = [
            COMPONENTS[c]
            for c, origin in enumerate(job["origin"])
            if origin == "usb"
            and job["mixed_ns"] + nvme[3 * i + c] - usb[3 * i + c] > clocks["mixed_ns"]
        ]
    return {
        "layer": group["layer"],
        "jobs": jobs,
        **clocks,
        "bytes_by_origin": bytes_by_origin,
        "gain_ns": clocks["nvme_ns"] - clocks["mixed_ns"],
        "nvme_last_experts": [j["expert"] for j in jobs if j["nvme_ns"] == clocks["nvme_ns"]],
        "mixed_last_experts": [j["expert"] for j in jobs if j["mixed_ns"] == clocks["mixed_ns"]],
    }


def pair(plan, usb, nvme):
    groups = []
    for g, u, n in zip(plan["groups"], usb["groups"], nvme["groups"], strict=True):
        row = group_oracle(g, u["pread_duration_ns"], n["pread_duration_ns"])
        row["observed_nvme_submit_to_ready_ns"] = n["elapsed_ns"]
        row["observed_usb_submit_to_ready_ns"] = u["elapsed_ns"]
        groups.append(row)
    totals = {
        key: sum(g[key] for g in groups) for key in ("nvme_ns", "usb_ns", "mixed_ns", "gain_ns")
    }
    breakdown = {}
    for single, label in ((True, "single"), (False, "multi")):
        part = [g for g in groups if (len(g["jobs"]) == 1) == single]
        breakdown[label] = {
            "groups": len(part),
            "advanced_groups": sum(g["gain_ns"] > 0 for g in part),
            "nvme_ns": sum(g["nvme_ns"] for g in part),
            "mixed_ns": sum(g["mixed_ns"] for g in part),
            "gain_ns": sum(g["gain_ns"] for g in part),
        }
    amounts = {
        origin: {
            field: sum(g["bytes_by_origin"][origin][field] for g in groups)
            for field in ("calls", "logical", "requested")
        }
        for origin in ("usb", "nvme")
    }
    require(
        sum(item["logical"] for item in amounts.values()) == plan["logical_bytes"]
        and sum(item["requested"] for item in amounts.values()) == plan["aligned_bytes"],
        "mixed byte conservation",
    )
    return dict(
        **totals,
        gain_fraction=totals["gain_ns"] / totals["nvme_ns"],
        share_nvme_ns_in_multi=breakdown["multi"]["nvme_ns"] / totals["nvme_ns"],
        breakdown=breakdown,
        bytes_by_origin=amounts,
        groups=groups,
        reaches_five_percent=20 * totals["gain_ns"] >= totals["nvme_ns"],
    )


def decision(passes):
    require(len(passes) == 2 and all(type(p) is bool for p in passes), "paired signs")
    if all(passes):
        return "GO_SMALL_MIXED_IO_FIXTURE_ONLY"
    if any(passes):
        return "INCONCLUSIVE"
    return "NO_GO_ORIGIN_SELECTION_FIXED_COMPONENT_SERVICE"


def analyse(raw_dir):
    base = HERE.parent / "nvme_admission"
    sources = {key: authenticated(base / key, sha) for key, sha in PINS.items()}
    plan = json.loads(sources["io_pair/plan.json"])
    public = json.loads(sources[PUBLIC_RECEIPT])
    validate_plan(plan)
    manifest = public["local_manifest"]
    require(set(manifest) == {*ARM_NAMES, "receipt.json", "freeze.json"}, "raw manifest")
    missing = [key for key in manifest if not (raw_dir / key).is_file()]
    if missing:
        raise MissingRaw({key: manifest[key] for key in missing})
    # Authenticate every arm before interpreting durations.
    inputs = {
        key: authenticated(raw_dir / key, spec["sha256"], spec["bytes"])
        for key, spec in manifest.items()
    }
    family = json.loads(inputs["receipt.json"])
    for field in (
        "arm_service_ns",
        "arm_wall_ns",
        "forward_passes",
        "all_payload_hashes_equal",
        "payload_manifest_sha256",
        "disk_delta",
    ):
        require(family[field] == public["receipt"][field], "family field: " + field)
    payloads = public["payload_sha256_in_plan_order"]
    require(
        len(payloads) == 60
        and all(len(h) == 64 for h in payloads)
        and family["forward_passes"] == 0
        and family["all_payload_hashes_equal"] is True,
        "historical family",
    )
    require(
        digest("\n".join(payloads).encode()) == family["payload_manifest_sha256"],
        "payload manifest",
    )
    arms = [json.loads(inputs[key]) for key in ARM_NAMES]
    for i, (origin, arm) in enumerate(zip(("usb", "nvme", "nvme", "usb"), arms, strict=True)):
        validate_arm(plan, arm, origin, payloads)
        reference = public["arms"][i]
        require(
            origin == reference["transport"]
            and arm["service_ns"] == reference["service_ns"] == family["arm_service_ns"][i],
            "arm service",
        )
        require(
            arm["arm_wall_ns"] == reference["arm_wall_ns"] == family["arm_wall_ns"][i], "arm wall"
        )
        for key in ("pread_sum_ns", "pread_union_ns"):
            require(sum(g[key] for g in arm["groups"]) == reference[key], "public " + key)
    pairs = {f"usb{u + 1}_nvme{n + 1}": pair(plan, arms[u], arms[n]) for u, n in ((0, 1), (3, 2))}
    return {
        "decision": decision([p["reaches_five_percent"] for p in pairs.values()]),
        "pairs": pairs,
        "arm_names_in_order": ARM_NAMES,
        "model": "SIMULATED_FIXED_COMPONENT_DURATIONS",
        "measurement_scope": "C135 call 3 position 2197; read service",
        "component_order": COMPONENTS,
        "historical_device_read_bytes_per_arm": [a["device_read_bytes"] for a in public["arms"]],
        "raw_manifest": manifest,
        "public_source_sha256": PINS,
        "payload_manifest_sha256": family["payload_manifest_sha256"],
    }


class MissingRaw(Exception):
    pass


def git(*args):
    return subprocess.check_output(
        ["git", "-c", "core.preloadIndex=false", "-c", "index.threads=1", *args],
        cwd=HERE,
        text=True,
    ).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    raw, out = args.raw_dir.resolve(), args.new_output_dir.resolve()
    repo = Path(git("rev-parse", "--show-toplevel"))
    if out.is_relative_to(raw) or out.is_relative_to(repo) or raw.is_relative_to(out):
        parser.error("output must be separate from the raw directory and the measurement checkout")
    for key, limit in (
        (resource.RLIMIT_AS, 256 << 20),
        (resource.RLIMIT_CPU, 60),
        (resource.RLIMIT_FSIZE, 2 << 20),
    ):
        _, hard = resource.getrlimit(key)
        resource.setrlimit(
            key, (min(hard, limit) if hard != resource.RLIM_INFINITY else limit, hard)
        )
    out.mkdir(mode=0o700, parents=False, exist_ok=False)
    receipt = {}
    status = 1
    try:
        receipt.update(
            commit=git("rev-parse", "HEAD"),
            tree=git("rev-parse", "HEAD^{tree}"),
            program_sha256=digest(Path(__file__).read_bytes()),
            protocol_sha256=PROTOCOL,
        )
        require(not git("status", "--porcelain"), "dirty checkout")
        authenticated(HERE / "protocol.md", PROTOCOL)
        receipt.update(analyse(raw), status="PASS")
        status = 0
    except MissingRaw as error:
        receipt.update(status="NOT_RUN_RAW_REQUIRED", missing_files=error.args[0])
    except Exception as error:
        receipt.update(status="FAIL_PRESERVED", error_type=type(error).__name__, reason=str(error))
    blob = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    require(len(blob) <= 2 << 20, "output size")
    pending = out / "receipt.pending"
    with pending.open("xb") as f:
        f.write(blob)
    pending.rename(out / "receipt.json")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
