"""Check C269 provenance and the availability of exact AR/B3 rows without opening weights."""

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PINS = {
    23: "d79d180a18cf6c0f0767d02307904e679c0edd4fa10c12a3256b87a398dd8002",
    32: "94b255e1cf05ea527cc08eb938b125f4ecd96699be53de6c5b9feb627db05461",
    102: "8baed0c5fe6f89d234107cf40e84fcb25bb2f77a7a682e3fac69be04bb7d7dfd",
    108: "b01d71b4518191bc4c44bf1ecc8542d06379c62eea4103160b574eac190ec08b",
}
CUTS = {"attn_post_norm": 2880, "ffn_moe_logits": 128}
EXTRA = ("attn_norm", "Qcur", "Kcur", "Vcur", "kqv_out", "attn_out", "ffn_inp")


def check(cond, why):
    if not cond:
        raise ValueError(why)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def pinned(path, h):
    b = path.read_bytes()
    check(sha(b) == h, "digest " + path.name)
    return b


def ar_rows(cap, member):
    rows = list(csv.DictReader(member(cap / "index.tsv").decode().splitlines(), delimiter="\t"))
    selected = {}
    for p in (189, 190):
        group = [r for r in rows if r["phase"] == f"decode{p - 189}" and r["first_abs"] == str(p)]
        check(
            not any(
                (r["layer"] == "24" and r["name"] == "l_out")
                or (r["layer"] == "25" and r["name"] in EXTRA)
                for r in group
            ),
            "extra AR cut",
        )
        for stage, n in CUTS.items():
            (target,) = [r for r in group if r["layer"] == "25" and r["name"] == stage]
            check(
                (target["type"], target["state_tokens"], target["ne"], target["nb"])
                == ("f32", "1", f"{n},1,1,1", f"4,{4 * n},{4 * n},{4 * n}"),
                "shape/stride",
            )
            fp = cap / target["file"]
            check(fp.parent == cap, "filename")
            b = member(fp)
            check(len(b) == int(target["bytes"]) == 4 * n, "length")
            selected[p, stage] = b
    return selected


def verify(arc, c7):
    src = c7 / "backends/c269-layer-last-use"
    protocol = (HERE / "protocol.md").read_text()
    pins = dict(re.findall(r"^\| ([^| ]+\.(?:cpp|cu)) \| ([0-9a-f]{64}) \|$", protocol, re.M))
    check(len(pins) == 6, "protocol source pins")
    for n, h in pins.items():
        pinned(src / n, h)
    manifests = {}
    for p, h in PINS.items():
        manifests[p] = json.loads(pinned(arc / f"part-{p}" / "manifest.json", h))["files"]

    def file(p, path):
        part = arc / f"part-{p}"
        info = manifests[p][str(path.relative_to(part))]
        b = pinned(path, info["sha256"])
        check(len(b) == info["bytes"], "archived size")
        return b

    c270 = arc / "part-23/tesy-c270-driver-20261125-r01/raw/tesy-c270-driver-20261125-r01.capture"
    authority = ar_rows(c270, lambda path: file(23, path))
    c127 = c7 / "results/c127-slots40-numeric-20260929T1654Z"
    pinned(
        c127 / "manifest.json", "cdb9201a72809a5acc2991f4d548eb675c8a6344e2d018a2f51979393fdce581"
    )
    for mode in ("on", "off"):
        check(
            ar_rows(c127 / "raw" / f"c127-slots40-{mode}01.capture", Path.read_bytes) == authority,
            "C127 subset does not reproduce independently sealed C270 values",
        )
    inventory = c7 / "results/c7-20260927T1130Z/raw/gguf-inventory.jsonl"
    weights = [
        r
        for r in map(
            json.loads,
            pinned(
                inventory, "2c8ca725f50000bf3177712cfa30d29a809f77f25826b425ea67d8fcbffd6d82"
            ).splitlines(),
        )
        if r.get("name", "").startswith("blk.25.") and "_exps." not in r["name"]
    ]
    stages = set(EXTRA) | set(CUTS)
    for p, modes in ((32, ["AR", "B3"]), (102, ["AR", "B3"]), (108, ["OFF", "ON"])):
        for arm in modes:
            files = [Path(f).name for f in manifests[p] if f"/{arm}/raw/" in f and ".capture/" in f]
            check(files, "empty capture in manifest")
            for stage in stages | {"l_out"}:
                layer = 24 if stage == "l_out" else 25
                for pos in (189, 190, 191):
                    row = f"{pos}.{stage}-{layer}.bin"
                    found = row in files or any(
                        n.startswith(f"decode{pos - 189}_{layer}_{stage}_") for n in files
                    )
                    check(
                        found == (p == 108 and stage == "ffn_moe_logits"),
                        "unexpected boundary coverage",
                    )
    base = arc / "part-108/tesy-b3-router-integrated-physical-20261125-r01"
    check(
        sha(file(108, base / "receipt.json"))
        == "27b97866f3d452786860f42133ffb247a9f06d95c904473aa2b09533de16c086",
        "integrated family",
    )
    present = {}
    for arm in ("OFF", "ON"):
        log = next((base / arm / "raw").glob("*.stderr"))
        stderr = file(108, log)
        for marker in (
            b"layer  24 assigned to device CPU, is_swa = 1",
            b"layer  25 assigned to device CUDA0, is_swa = 0",
            b"flash_attn    = enabled",
            b"layer  25: dev = CUDA0",
        ):
            check(marker in stderr, "run-specific placement")
        root = next((base / arm / "raw").glob("*.capture")) / "boundary"
        refs = {}
        for p in (189, 190, 191):
            y = file(108, root / f"{p}.ffn_moe_logits-25.bin")
            check(len(y) == 512, "router shape")
            d = {"hash": sha(y)}
            if p in (189, 190):
                au = authority[p, "ffn_moe_logits"]
                d["unequal_words_vs_AR"] = sum(
                    y[i : i + 4] != au[i : i + 4] for i in range(0, 512, 4)
                )
            refs[str(p)] = d
        present[arm] = refs
    return {
        "status": "AR_ROUTER_OPERAND_PRESENT_B3_OPERAND_UNOBSERVED",
        "worker_commit": "d0ebfbcc6c8f456bc1083027c1b08075a32824d8",
        "archive_manifests": PINS,
        "AR": {f"{p}.{name}": sha(b) for (p, name), b in authority.items()},
        "integrated_prebias": present,
        "C127_ON_OFF_reproduce_AR_subset": True,
        "inventory": {
            w["name"]: {k: w[k] for k in ("tensor_type", "shape", "n_bytes", "data_offset")}
            for w in weights
        },
    }


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--archive", type=Path, required=True)
    cli.add_argument("--c7", type=Path, required=True)
    args = cli.parse_args()
    print(json.dumps(verify(args.archive, args.c7), indent=2, sort_keys=True))
