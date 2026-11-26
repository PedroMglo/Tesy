"""Identify the selected GPT-OSS bias instance and its executor in the sealed tiny GPU fixture."""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

FAMILY = "2d165f3e9c8f8108a04e758a5496e610cdbe0051afaee1fe1da35123b8373bfd"
MODES = ("RESIDENT", "BANK9", "BANK7")
ROLES = {(layer, role) for layer in range(2) for role in ("gate", "up", "down")}


def need(ok, why):
    if not ok:
        raise ValueError(why)


def read(path, digest):
    body = path.read_bytes()
    need(hashlib.sha256(body).hexdigest() == digest, "digest mismatch for " + path.name)
    return body


def examine(raw):
    rows = [line.split() for line in raw.decode().splitlines() if line]
    original = {r[1]: r for r in rows if r[0] == "ORIG" and r[1].endswith("_exps.bias")}
    uploads = [r for r in rows if r[:2] == ["SET", "1"] and r[5].endswith("_exps.bias")]
    need(len(original) == len(uploads) == 6, "initial bias census")
    residents = {}
    for row in uploads:
        _, _, owner, _, _, name, dest, offset, size, source, file = row
        copies = [r for r in rows if r[:3] == ["COPY", "1", owner] and r[4] == "1"]
        need(
            len(copies) == 1
            and copies[0][5:] == [dest, source, size, file, "0"]
            and offset == "0"
            and size == original[name][3]
            and int(file) >= 0,
            "unattributed initial bias copy",
        )
        need(name not in residents, "duplicate initial bias upload")
        residents[name] = dest

    phases = {}
    for phase, title in (("3", "prefill32"), ("4", "teacher1")):
        nodes = [r for r in rows if r[:2] == ["NODE", phase]]
        submits = [r for r in rows if r[:2] == ["SUBMIT", phase]]
        by_node = {r[2]: r[3] for r in submits if r[4] == "0"}
        need(len(nodes) == len(submits) == len(by_node) == 12, "unpaired observed operators")
        ops = {}
        for row in nodes:
            _, _, node_id, kind, _, name, addr, _, _, source_tier, result_tier, _ = row
            role = re.fullmatch(
                r"(?:moe_cache\.)?blk\.(\d+)\.ffn_(up|down|gate)_exps\.(weight|bias)", name
            )
            need(
                role
                and kind in ("mm", "bias")
                and role[3] == {"mm": "weight", "bias": "bias"}[kind],
                "logical component",
            )
            key = int(role[1]), role[2], kind
            need(key not in ops and by_node[node_id] == result_tier, "ambiguous executor")
            source_class = source_tier
            if kind == "bias":
                if source_tier == "CUDA0":
                    need(addr == residents[name], "different device bias address")
                    source_class = "startup_cuda"
                else:
                    orig = original[name]
                    need(
                        source_tier == orig[-1] == "CPU" and addr == orig[2] and int(orig[4]) >= 0,
                        "different mapped bias address",
                    )
                    source_class = "mapped_cpu"
            ops[key] = (by_node[node_id], source_class)
        pairs, sources = Counter(), Counter()
        for layer, role in sorted(ROLES):
            mm, _ = ops[layer, role, "mm"]
            bias, placement = ops[layer, role, "bias"]
            pairs[f"{mm}_MMID_to_{bias}_ADD_ID"] += 1
            sources[placement] += 1
        phases[title] = dict(operator_pairs=pairs, bias_sources=sources)
    return phases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family", type=Path)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(read(args.family / "receipt.json", FAMILY))
    need(manifest["status"] == "PASS_TINY_HYBRID_GPU_FIXTURE", "unqualified family")
    args.new_output_dir.mkdir(mode=0o700)
    modes = {}
    for arm in MODES:
        key = arm + "/stdout"
        modes[arm] = examine(read(args.family / key, manifest["raw_sha256"][key]))
    record = dict(status="REPRODUCED_TINY_BIAS_PLACEMENT", family_sha256=FAMILY, modes=modes)
    with (args.new_output_dir / "receipt.json").open("x") as f:
        json.dump(record, f, sort_keys=True, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
