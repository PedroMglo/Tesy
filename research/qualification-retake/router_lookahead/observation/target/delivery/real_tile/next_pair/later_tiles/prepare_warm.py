"""Materialize CPU0→1 inputs for the sealed warm case from the selected raw and bias-only ranges."""

import argparse
import json
import os
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
S = run_path(str(HERE / "select_pair.py"))
P, need, sha, blob = (S[k] for k in ("P", "need", "sha", "blob"))
STATE = "45cdefb3b05b0becb30555b22263084d63ea94d16680346947aab2637c543860"
PLAN = "15e54e258c108743138e40309c425cb2478d563c58635a54375cf1a2916f82d1"
WARM = "b39fe01389881e7c3a8113097b112dedee0e7cdbd1e61e03c6c927791d67020a"
COLD = "3a297711d38e9ff3ea4a2f29cb4bab1eb90677759e17e283b237c9ac90691752"
CONTRACT = "ee0e75682b12b67a085a2645b4ca605c7e771e3dccbb55d9d41ff0cfdf6a293c"


def bias_range(rec, role):
    layer, e = rec["layer"], rec["expert"]
    size = 2880 * 4
    c = rec["components"][3 + role]
    need(
        layer in (0, 1)
        and 0 <= e < 128
        and rec["pack_offset"] == (layer * 128 + e) * P["STRIDE"]
        and c["packed_relative_offset"] == P["WINDOW"] + role * size
        and c["name"] == f"blk.{layer}.ffn_{P['ROLES'][role]}_exps.bias"
        and c["type"] == "f32"
        and c["size_bytes"] == size
        and c["packed_relative_offset"] + size <= P["STRIDE"]
        and len(bytes.fromhex(c["sha256"])) == 32,
        "bias-only component extent",
    )
    return rec["pack_offset"] + c["packed_relative_offset"], size, c["sha256"]


def prepare(a, io):
    need(sha((HERE / "prepare.md").read_bytes()) == CONTRACT, "preparation contract")
    parent = json.loads(io.sealed(a.state_dir / "receipt.json", STATE))
    plan = json.loads(io.sealed(a.state_dir / "input-plan.json", PLAN))
    cold = json.loads(io.sealed(a.cold_dir / "prepare.json", COLD))
    names = set(cold["file_sha256"])
    need(
        len(names) == 71
        and parent["status"] == "WARMSLOT_DECISIONS_REPRODUCED"
        and plan["files_sha256"]["warm-state.json"] == WARM
        and {**plan["files_sha256"], "input-plan.json": PLAN} == parent["files_sha256"],
        "state authorities",
    )
    # The selector omitted the source router, which is common to both tiles.
    for f in ("L0.router.f32", "L0.bias.f32"):
        data = io.sealed(a.cold_dir / f, cold["file_sha256"][f])
        P["finite"](data)
        io.emit(f, data)
    marks = None
    for f, ref in plan["files_sha256"].items():
        need(f in names or f == "warm-state.json", "unexpected tensor")
        data = io.sealed(a.state_dir / f, ref)
        io.emit(f, data)
        if f == "warm-state.json":
            marks = json.loads(data)
    need(marks is not None and marks["source_boundary"]["record"] == 50696, "source cut")
    idx = plan["store"]
    manifest = json.loads(io.sealed(a.manifest_dir / "receipt.json", P["DERIVED"]))
    need(
        idx["index_sha256"] == manifest["index_sha256"]
        and idx["pack_sha256"] == manifest["pack_sha256"]
        and idx["pack_stat"] == manifest["pack_stat"],
        "placement authority",
    )
    path = Path(manifest["pack_path"])
    need(path.resolve(strict=True) == path, "pack canonical location")
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        need(P["identity"](os.fstat(fd)) == idx["pack_stat"], "open pack identity")
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_RANDOM)
        for layer in (0, 1):
            active = plan["active_experts"][str(layer)]
            need(
                active == sorted(set(active)) and len(active) == (50, 40)[layer],
                "active expert keys",
            )
            for role, name in enumerate(P["ROLES"]):
                dense = bytearray(2880 * 4 * 128)
                for expert in active:
                    rec = idx["records"][f"{layer}/{expert}"]
                    offset, size, ref = bias_range(rec, role)
                    io.charge(size, "pack_bias")
                    values = os.pread(fd, size, offset)
                    io.returned["pack_bias"] += len(values)
                    need(len(values) == size and sha(values) == ref, "bias FD bytes")
                    P["finite"](values)
                    dense[expert * size : (expert + 1) * size] = values
                io.emit(f"L{layer}.{name}.bias.f32", dense)
        need(
            P["identity"](os.fstat(fd)) == P["identity"](path.stat()) == idx["pack_stat"],
            "pack final stat",
        )
    finally:
        os.close(fd)
    need(
        set(io.files) == names | {"warm-state.json"}
        and io.reads == io.returned
        and io.returned["pack_bias"] == 3_110_400,
        "materialized input contract",
    )

    def address(layer, expert):
        rec = idx["records"][f"{layer}/{expert}"]
        return dict(
            layer=layer,
            expert=expert,
            pack_offset=rec["pack_offset"],
            hashes=[c["sha256"] for c in rec["components"][:3]],
        )

    entries = []
    warm = []
    for layer in (0, 1):
        for r in plan["official_reservations"][str(layer)]:
            entries.append(address(layer, r["expert"]) | r)
        for s in marks["source_boundary"]["pools"][str(layer)]["slots"]:
            need(
                s["state"] == 2 and s["claim"] is None and s["origin"] is not None, "ready binding"
            )
            warm.append(
                address(layer, s["expert"])
                | dict(slot=s["slot"], gen=s["generation"], slot_last_use=s["slot_last_use"])
            )
    offers = parent["offers"]
    offer_records = [address(1, e) | {"consumed": e not in parent["unused"]} for e in offers]
    false_records = [r for r in offer_records if not r["consumed"]]
    need(
        len(entries) == 32
        and [(r["layer"], r["slot"]) for r in warm]
        == [(layer, s) for layer in (0, 1) for s in range(40)]
        and len(false_records) == 3,
        "entry counts",
    )
    return dict(
        status="PASS_REAL_TILE_WARM_INPUT",
        program_sha256=sha(Path(__file__).read_bytes()),
        protocol_sha256=CONTRACT,
        authorities=parent["authorities"]
        | {"state_receipt": STATE, "input_plan": PLAN, "state": WARM, "cold": COLD},
        file_sha256=io.files.copy(),
        weight_bases=[idx["weight_bases"][str(lay)] for lay in (0, 1)],
        pack_stat=idx["pack_stat"],
        offers=offers,
        entries=entries,
        warm_records=warm,
        offer_records=offer_records,
        false_records=false_records,
        initial_policy=marks["source_boundary"],
        terminal_policy=marks["last_wave"],
        call=1,
        tile=5,
        positions=[128, 159],
        pack_bias_reads=270,
        weight_matrix_read_bytes=0,
        gguf_read_bytes=0,
        requested_bytes=dict(io.reads),
        returned_bytes=dict(io.returned),
        verified_c270_byte_checks=sum(r["sampled_byte_checks"] for r in parent["golds"].values()),
        golds=parent["golds"],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("state-dir", "cold-dir", "manifest-dir", "new-output-dir"):
        parser.add_argument("--" + field, type=Path, required=True)
    a = parser.parse_args()
    a.new_output_dir.mkdir(mode=0o700, exist_ok=False)
    io = P["Inputs"](a.new_output_dir)
    try:
        receipt = prepare(a, io)
    except Exception as e:
        receipt = dict(
            status="FAIL_PRESERVED",
            reason=str(e),
            requested_bytes=dict(io.reads),
            returned_bytes=dict(io.returned),
            file_sha256=io.files.copy(),
        )
    io.emit("prepare.json", blob(receipt))
    print(receipt["status"], receipt.get("reason", ""))
    return int(receipt["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
