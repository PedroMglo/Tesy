"""Seal a private ordered I/O workload for the selected causal policy's 46 decode evaluations."""

import argparse
import hashlib
import json
import os
import resource
import signal
import subprocess
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
dc = run_path(HERE.parent / "screen.py")
prev = dc["previous"]
need, sha = dc["need"], dc["sha"]
full = run_path(prev["INT"] / "t1_full_pack_service/measure.py")
DERIVE = run_path(prev["INT"].parents[1] / "packed_nvme_manifest/derive.py")
PRICE = "f637152c0915ccbf33d4f70e101e9910a6aab2edd2d925a93f7ed6f250fe8f99"
PLACEMENT = "adc58125a13aa286371c127f41bf67b0ed4756e9ec2dc08bd2cb6e7ed754a000"
MODEL = "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"
ROLES = ("gate", "down", "up")


def encode(obj):
    return json.dumps(obj, separators=(",", ":"), sort_keys=True, allow_nan=False).encode()


def digest(obj):
    return hashlib.sha256(encode(obj)).hexdigest()


def metadata(index, bases):
    need(
        index["stride"] == full["STRIDE"]
        and index["weight_window"] == full["WINDOW"]
        and index["pack_bytes"] == full["SIZE"]
        and index["pack_sha256_write_stream"] == full["PACK"]
        and index["model_sha256_previous_verified"] == MODEL
        and index["alignment"] == 4096,
        "integral model/pack identity",
    )
    meta = {(layer, k): tuple(c) for layer, line in enumerate(bases) for k, c in enumerate(line)}
    DERIVE["verify_descriptors"](index, meta, ROLES)


def components(entry, positions):
    fields = []
    for k, role in enumerate(ROLES):
        w = entry["components"][k]
        off, n = w["source_offset"], w["size_bytes"]
        base, slab = positions[k]
        need(
            off == base + entry["expert"] * slab
            and n == slab == 4406400
            and w["packed_relative_offset"] == k * slab
            and w["type"] == "mxfp4"
            and w["name"] == f"blk.{entry['layer']}.ffn_{role}_exps.weight"
            and len(bytes.fromhex(w["sha256"])) == 32,
            "component binding",
        )
        head = off % 4096
        aligned = (head + n + 4095) // 4096 * 4096
        need(off - head + aligned <= 63387346208, "reading past GGUF EOF")
        fields.append(
            dict(
                role=role,
                source_offset=off,
                size_bytes=n,
                aligned_offset=off - head,
                aligned_bytes=aligned,
                packed_relative_offset=w["packed_relative_offset"],
                sha256=w["sha256"],
            )
        )
    return fields


def attest_order(groups, jobs):
    start = next(iter(jobs))[0]
    tail = [g for g in groups if g["site"][0] >= start]
    need(list(jobs) == [g["site"] for g in tail], "missing or reordered callback")
    for group in tail:
        ranks = group["ranks"]
        assigned = jobs[group["site"]]
        need(
            len(ranks) == len(set(ranks)) == 4
            and list(assigned) == [e for e in ranks if e in assigned],
            "admissions out of order against causal ranks",
        )


def stages(jobs, obs, bank, bases, index):
    groups = []
    first = next(iter(jobs))[0]
    for (call, tile, layer, wave), choices in jobs.items():
        step, expected_layer = divmod(len(groups), 36)
        need((call, tile, layer, wave) == (first + step, 1, expected_layer, -1), "callback order")
        row = dict(
            step=step,
            position=2197 + step,
            call=call,
            tile=tile,
            layer=layer,
            wave=wave,
            tier="CPU" if layer < 25 else "CUDA0",
            jobs=[],
        )
        for ordinal, (e, (slot, gen)) in enumerate(choices.items()):
            entry = index["experts"][128 * layer + e]
            need(
                (entry["layer"], entry["expert"], entry["pack_offset"])
                == (layer, e, (128 * layer + e) * full["STRIDE"]),
                "index place",
            )
            old = obs[(call, tile, layer, wave)].get(e)
            s, g, r, t = old if old is not None else (None, None, None, None)
            job = dict(
                ordinal=ordinal,
                expert=e,
                slot=slot,
                generation=gen,
                source="bank" if e in bank[layer] else "disk",
                pack_offset=entry["pack_offset"],
                pack_bytes=full["WINDOW"],
                components=components(entry, bases[layer]),
                r0_same_site_slot=s,
                r0_same_site_generation=g,
                r0_same_site_read_ns=r,
                r0_same_site_set_ns=t,
            )
            row["jobs"].append(job)
        groups.append(row)
    return groups


def certify(plan, counts):
    need(len(plan) == 46 * 36, "decode groups missing")
    start = plan[0]["call"]
    summary = {"CPU": Counter(), "CUDA0": Counter()}
    reconstructed = Counter()
    disk = []
    for i, g in enumerate(plan):
        step, layer = divmod(i, 36)
        need(
            (g["step"], g["position"], g["call"], g["tile"], g["layer"], g["wave"])
            == (step, 2197 + step, start + step, 1, layer, -1)
            and g["tier"] == ("CPU" if layer < 25 else "CUDA0"),
            "site grid",
        )
        jobs = g["jobs"]
        need(
            len(jobs) <= 4
            and len({j["expert"] for j in jobs}) == len(jobs)
            and len({j["slot"] for j in jobs}) == len(jobs),
            "rank or slot alias",
        )
        same = summary[g["tier"]]
        same["all_groups"] += 1
        same["empty_admission_groups"] += not jobs
        same["empty_disk_groups"] += not any(j["source"] == "disk" for j in jobs)
        chains = {x: [] for x in (0, 4, 5)}
        disk.append([])
        for n, j in enumerate(jobs):
            need(
                j["ordinal"] == n
                and j["source"] in ("disk", "bank")
                and 0 <= j["expert"] < 128
                and 0 <= j["slot"] < 40
                and j["generation"] > 0,
                "reservation identity",
            )
            r, t = j["r0_same_site_read_ns"], j["r0_same_site_set_ns"]
            common = r is not None
            need(
                common
                == (t is not None)
                == (j["r0_same_site_slot"] is not None)
                == (j["r0_same_site_generation"] is not None)
                and (not common or r >= 0 and t >= 0),
                "incomplete matched prices",
            )
            if j["source"] == "disk":
                need(common, "unobserved price on a disk job")
                disk[-1].append(
                    [j["ordinal"], j["expert"], j["slot"], j["generation"], j["pack_offset"]]
                )
                same["disk_pack_requested_bytes"] += j["pack_bytes"]
                same["disk_gguf_requested_bytes"] += sum(
                    x["aligned_bytes"] for x in j["components"]
                )
            same["admissions"] += 1
            same[j["source"] + "_jobs"] += 1
            same["common_jobs" if common else "new_jobs"] += 1
            for scale, values in chains.items():
                values.append(5 * (t or 0) + (scale * (r or 0) if j["source"] == "disk" else 0))
        for scale, values in chains.items():
            reconstructed[scale] += dc["lower"](values)
    for tier, c in summary.items():
        ref = counts["gguf_1_same_tier"]["by_tier"]["cpu" if tier == "CPU" else "cuda"]
        for k in (
            "admissions",
            "disk_jobs",
            "new_jobs",
            "common_jobs",
            "disk_pack_requested_bytes",
            "disk_gguf_requested_bytes",
            "bank_jobs",
        ):
            need(c[k] == ref["host_bank_jobs" if k == "bank_jobs" else k], "volume or population")
    for scale, label in ((0, "unidentified_pack"), (4, "gguf_0p8"), (5, "gguf_1")):
        need(
            reconstructed[scale] // 20 == counts[label + "_same_tier"]["inside_lower_ns"],
            "job/time association",
        )
    return dict(
        tiers={k: dict(v) for k, v in summary.items()},
        ordered_disk_sha256=digest(disk),
        ordered_groups_sha256=digest(plan),
        inside_ns={str(k): n // 20 for k, n in reconstructed.items()},
    )


def execute(a):
    price = dc["cost"]["pinned"](HERE.parent / "evidence/receipt.json", PRICE)
    replay = dc["cost"]["pinned"](dc["REPLAY"] / "evidence/receipt.json", dc["REPLAY_SHA"])
    placement = full["read"](a.placement, PLACEMENT)
    full["validate_placement"](placement)
    rows, slots, words, calls, interval, bank, bases, origin = prev["sources"](
        a.family, dc["FAMILY"]
    )
    need(all(origin[k] == replay[k] for k in origin), "original inputs")
    index = full["read"](a.index, full["INDEX"])
    metadata(index, bases)
    group, reads, workers = prev["segment"](rows)
    need(workers == replay["observed"], "actual R0 services")
    args = reads, slots, words, calls, interval, bank, bases
    ref, record, original = dc["capture"](group, args, "r0", None)
    need(record == replay["r0"], "same R0 decisions")
    _, alt, jobs = dc["capture"](group, args, "carry", ref)
    need(
        alt == {k: v for k, v in replay["carry"].items() if k != "comparison"},
        "same causal trajectory",
    )
    attest_order(group, jobs)
    groups = stages(jobs, dc["measurements"](rows, original), bank, bases, index)
    report = certify(groups, price["results"]["carry"]["bank"])
    plan = dict(
        schema="tesy-natural-decode-transport-v1",
        groups=groups,
        model_sha256=MODEL,
        pack_sha256=full["PACK"],
        index_sha256=full["INDEX"],
        family_sha256=dc["FAMILY"],
        clock_sha256=PRICE,
        policy_sha256=origin["policy_sha256"],
        prefix_sha256=origin["prefix_sha256"],
        component_order=list(ROLES),
        causal_slot_stream_sha256=alt["inferred_slot_stream_sha256"],
    )
    raw = encode(plan) + b"\n"
    need(len(raw) < 8 << 20, "output cap")
    with (a.new_output_dir / "plan.json").open("xb") as stream:
        stream.write(raw)
    return report | dict(
        status="PASS_ORDERED_DECODE_TRANSPORT_PLAN",
        plan_bytes=len(raw),
        plan_sha256=sha(a.new_output_dir / "plan.json"),
        family_sha256=dc["FAMILY"],
        clock_sha256=PRICE,
        policy_sha256=origin["policy_sha256"],
        placement_sha256=PLACEMENT,
        model_sha256=MODEL,
        pack_sha256=full["PACK"],
        index_sha256=full["INDEX"],
        model_bytes_read=0,
        pack_bytes_read=0,
        model_launches=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("family", "index", "placement", "new-output-dir"):
        p.add_argument("--" + k, required=True, type=Path)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        git = [
            "git",
            "--no-optional-locks",
            "-c",
            "core.preloadIndex=false",
            "-c",
            "index.threads=1",
            "-C",
            str(HERE),
        ]
        need(not subprocess.check_output([*git, "status", "--porcelain"]), "unclean")
        resource.setrlimit(resource.RLIMIT_AS, (768 << 20, 768 << 20))
        resource.setrlimit(resource.RLIMIT_CPU, (118, 120))
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("120s wall")))
        signal.alarm(120)
        result = execute(a) | dict(
            protocol_sha256=sha(HERE / "protocol.md"),
            program_sha256=sha(Path(__file__)),
            commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
            tree=subprocess.check_output([*git, "rev-parse", "HEAD^{tree}"], text=True).strip(),
        )
    except Exception as exc:
        result = dict(status="FAIL_PRESERVED", failure=f"{type(exc).__name__}: {exc}")
    finally:
        signal.alarm(0)
    with (a.new_output_dir / "receipt.json").open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(result["status"], result.get("failure", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
