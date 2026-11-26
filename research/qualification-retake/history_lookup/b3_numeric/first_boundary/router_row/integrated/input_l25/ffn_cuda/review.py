"""Reopen the two complete target families and independently reconcile the routed fixture."""

import argparse
import json
import struct
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
RUN = run_path(str(HERE / "run.py"))
D, R, need, read, sha, save = (RUN[k] for k in ("D", "R", "need", "read", "sha", "save"))
BUILD = "717da62c518b9afe38eb05c0dd2d6224cf9aa401a3eaac6295f9a08d5935493a"
PHYSICAL = "6e2103047c068ab7258f5e2617bc6eba9f559efc84fed3e8658d6f7450c41fe9"


def review(a):
    b, r = R["reopen"](a.build, BUILD), R["reopen"](a.run, PHYSICAL)
    need(
        b["status"] == "BUILT_ROUTED_FFN"
        and b["protocol_sha256"] == D["METHOD"] == sha(HERE / "protocol.md")
        and r["commit"] == b["commit"]
        and r["tree"] == b["tree"]
        and r["build_sha256"] == BUILD
        and r["operator_starts"] == 1
        and r["model_forwards"] == 0
        and all(sha(HERE / k) == v for k, v in r["sources"].items())
        and r["sources"] == b["sources"]
        and sha(a.build / "fixture") == b["elf_sha256"],
        "method and ELF",
    )
    inputs, refs = D["references"](a.serial, a.block)
    local = a.build / "inputs"
    for file, data in (inputs | {k + ".gold": v for k, v in refs.items()}).items():
        need((local / file).read_bytes() == data, "target bridge " + file)
    ids = list(struct.unpack("<12i", inputs["logical.i32"]))
    need(
        b["routed_ids"] == ids and sha(a.inventory) == D["BASE"]["INVENTORY"],
        "ID/inventory authority",
    )
    inventory = map(json.loads, a.inventory.read_bytes().splitlines())
    inv = {row["name"]: row for row in inventory if row.get("name")}
    ranges = read(a.build / "ranges.json")
    wanted = {
        f"{role}.{suffix}.{e}" for role in D["ROLES"] for suffix in ("weight", "bias") for e in ids
    }
    need(
        set(ranges) == wanted and b["ranges_sha256"] == sha(a.build / "ranges.json"),
        "all routed ranges",
    )
    payload = {"weight": 0, "bias": 0}
    for name, record in ranges.items():
        role, suffix, expert = name.split(".")
        src = inv[f"blk.25.ffn_{role}_exps.{suffix}"]
        size = src["n_bytes"] // 128
        need(
            record
            == dict(
                tensor=src["name"],
                expert=int(expert),
                offset=src["data_offset"] + int(expert) * size,
                bytes=size,
                sha256=sha(local / name),
            )
            and (local / name).stat().st_size == size,
            "sealed range " + name,
        )
        payload[suffix] += size
    need(sum(payload.values()) == b["input_model_payload_B"], "input byte census")
    outputs = {k: (a.run / "device" / (k + ".f32")).read_bytes() for k in D["TAGS"]}
    grade = D["grade"](outputs, refs, ids)
    need(
        grade == read(a.run / "grade.json")
        and sha(a.run / "grade.json") == r["grade_sha256"]
        and r["status"] == grade["decision"],
        "recorded grade",
    )
    for k, data in outputs.items():
        for key, target in refs.items():
            got = struct.unpack("<8640I", data)
            gold = struct.unpack("<8640I", target)
            counts = [
                sum(got[j] != gold[j] for j in range(start, start + 2880))
                for start in (0, 2880, 5760)
            ]
            need(
                counts == [row["different"] for row in grade["rows"][k][key]],
                "independent words by position",
            )
    cuda = "libggml-cuda.so.0.15.3"
    need(
        all(r["loaded"][k][cuda] == b["permitted_providers"][cuda] for k in ("before", "after"))
        and r["after_exit"]["gpu"]["used_mib"] == r["admission"]["gpu"]["used_mib"],
        "live CUDA and release",
    )
    return dict(
        decision=r["status"],
        grade=grade,
        rows_ids=[ids[i : i + 4] for i in range(0, 12, 4)],
        expert_union=len(set(ids)),
        original_gguf_ranges=len(ranges),
        bytes=payload,
        protocol_sha256=D["METHOD"],
        commit=r["commit"],
        tree=r["tree"],
        elf_sha256=b["elf_sha256"],
        model_sha256=b["model_sha256"],
        cuda_sha256=b["permitted_providers"][cuda],
        grade_sha256=r["grade_sha256"],
        inputs={k: r[k] for k in ("block_sha256", "serial_sha256", "build_sha256")},
        physical_sha256=PHYSICAL,
        model_forwards=r["model_forwards"],
        CUDA_processes=r["operator_starts"],
        build_s=b["wall_s"],
        physical_scope_s=r["wall_s"],
        cgroup_peak_B=r["cgroup_peak_B"],
        gpu_used_MiB={
            k: v["gpu"]["used_mib"]
            for k, v in (
                r["live"] | dict(admission=r["admission"], after_exit=r["after_exit"])
            ).items()
        },
        device=r["device"],
        samples={k: r[k] for k in ("admission", "live", "after_exit")},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("serial", "block", "build", "run", "inventory", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    args = p.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    result = review(args)
    save(args.new_output_dir / "result.json", result)
    print(result["decision"])
