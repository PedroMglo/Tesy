"""Reopen the shape-one C127 FFN witness and bind it to C270 and four C290 records."""

import argparse
import csv
import hashlib
import json
import math
import os
import re
import resource
import signal
import stat
import struct
import subprocess
import sys
from io import StringIO
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "tools/c127_slots40_numeric.py").is_file())
QUAL = REPO / "research/qualification-retake"
schema = run_path(QUAL / "packed_real_layer/prepare.py")
need, sha, read = (schema[n] for n in ("need", "file_sha", "authenticated"))
C127 = "c127-slots40-numeric-20260929T1654Z"
C270 = schema["C270"]
RID = "c127-ref-l00-01"
IDS = (28, 24, 8, 16)
SLOTS = (3, 14, 6, 35)
IDS_SHA = "8fb3aff447febaeaa5a8bdd0c485fd20d51d39fb6ac3e6ba4849eb4a664dbc23"
C127_PROTOCOL = "dcb676daf107464fc7017e17685b53df0f5177d02c4676cab634d51ce9625ca2"
C127_MANIFEST = "cdb9201a72809a5acc2991f4d548eb675c8a6344e2d018a2f51979393fdce581"
DROOT = "cd4c0665c5485268cddfc7dba576b1cf490222c120cf34f72d555a6cbccbc5b9"
PLACEMENT = "adc58125a13aa286371c127f41bf67b0ed4756e9ec2dc08bd2cb6e7ed754a000"
PREP = "a3a6028b45719ee0a1c63f689a2e6896b5a401ee394d5aa9d3188d98e72dc269"
ROLES = ("gate", "down", "up")
# C127 canonical probes index gate/up/down for weights and biases.
C127_INDEX = (0, 2, 1, 3, 5, 4)
SHAPES = {
    "attn_post_norm": (2880, 1, 1, 1),
    "ffn_moe_logits": (128, 1, 1, 1),
    "ffn_moe_probs": (128, 1, 1, 1),
    "ffn_moe_topk": (4, 1, 1, 1),
    "ffn_moe_topk_stream": (4, 1, 1, 1),
    "ffn_moe_weights_softmax": (1, 4, 1, 1),
    "ffn_moe_out": (2880, 1, 1, 1),
}


def blob_sha(blob):
    return hashlib.sha256(blob).hexdigest()


def sealed(path, h):
    return json.loads(read(path, h))


def write(path, data):
    with path.open("xb") as f:
        f.write(data)
    h = blob_sha(data)
    need(sha(path) == h, "output readback")
    return h


def table(data):
    return list(csv.DictReader(StringIO(data.decode()), delimiter="\t"))


def row_authority(rec, selected):
    need(
        rec["layer"] == 0
        and rec["device"] == "cpu"
        and rec["all_bitwise"] is True
        and rec["canonical_layer_bytes"] == 1_697_956_352
        and rec["numeric_rows"] == 7,
        "resident layer scope",
    )
    rows = [row for row in rec["rows"] if row["phase"] == selected]
    need(len(rows) == 1, "resident row missing or duplicate")
    row = rows[0]
    need(
        row["state"] == "NUMERIC"
        and row["tokens"] == 1
        and all(
            row[k] is True for k in ("routing_ids_equal", "routing_weights_bitwise", "ffn_bitwise")
        )
        and all(
            row[k] == 0
            for k in (
                "ffn_max_abs",
                "ffn_rmse",
                "ffn_nonfinite",
                "routing_weights_max_abs",
                "routing_weights_rmse",
                "routing_weights_nonfinite",
            )
        ),
        "resident row fidelity",
    )


def resident(results):
    project = REPO / "results" / C127
    proto = sealed(project / "protocol.json", C127_PROTOCOL)
    manifest = sealed(project / "manifest.json", C127_MANIFEST)
    h = manifest["receipts_sha256"][RID]
    r = sealed(project / (RID + "-receipt.json"), h)
    root = results / C127 / "raw"
    monitor = sealed(root / (RID + ".json"), manifest["raw_manifests"][RID])
    command = monitor["command"]
    cap = root / "c127-slots40-on01.capture"
    need(
        r["status"] == "PASS_CANONICAL_LAYER"
        and r["layer"] == 0
        and r["run_id"] == RID
        and r["scope_returncode"] == monitor["returncode"] == 0
        and monitor["stop_reason"] is None
        and r["raw_manifest_sha256"] == manifest["raw_manifests"][RID]
        and monitor["mapped_libraries_match_ldd"] is True
        and monitor["artifact_identity"]["sha256_previously_verified"] == schema["MODEL"]
        and monitor["binary_sha256"] == proto["reference_binary_sha256"]
        and sha(REPO / "tools/c7_layer_reference.cpp") == proto["reference_source_sha256"]
        and proto["numeric_ids_sha256"] == IDS_SHA
        and command[0] == proto["reference_binary_path"]
        and len(command) == 6
        and Path(command[2]).parts[-3:] == (C127, "raw", cap.name)
        and command[3:] == ["0", "--ngl", "12"],
        "C127 real resident process",
    )
    need(r["reference_sha256"] == monitor["output_sha256"][".stdout"], "stdout binding")
    row_authority(sealed(root / (RID + ".stdout"), r["reference_sha256"]), "decode0")
    need(
        sha(REPO / "tools/c94_session_wave_8k_reference.py")
        == "4f63c7e38143ca3130029ad443a4abeb1580b62799857b8984685742bb073c68",
        "original tree verifier",
    )
    sys.path.insert(0, str(REPO / "tools"))
    from c94_session_wave_8k_reference import tree_digest

    need(
        not cap.is_symlink() and all(stat.S_ISREG(p.lstat().st_mode) for p in cap.iterdir()),
        "indirect capture file",
    )
    tree = tree_digest(cap)
    need(
        tree == r["capture_tree"] == manifest["capture_trees"]["on"]
        and tree["files"] == 3266
        and tree["total_bytes"] == 88704231,
        "resident input tree",
    )
    return cap, dict(
        tree=tree,
        layer_receipt=h,
        stdout=r["reference_sha256"],
        monitor=r["raw_manifest_sha256"],
        operator=monitor["binary_sha256"],
        source=proto["reference_source_sha256"],
    )


def select_stages(index):
    rows = [r for r in index if r["phase"] == "decode0" and r["layer"] == "0"]
    need(len(rows) == len(SHAPES) and {r["name"] for r in rows} == set(SHAPES), "stage coverage")
    info = {}
    for r in rows:
        name = r["name"]
        shape = tuple(map(int, r["ne"].split(",")))
        ids = name in ("ffn_moe_topk", "ffn_moe_topk_stream")
        need(
            shape == SHAPES[name]
            and r["type"] == ("i32" if ids else "f32")
            and int(r["bytes"]) == 4 * math.prod(shape)
            and (r["chunk"], r["first_abs"], r["state_tokens"]) == ("-1", "189", "1")
            and Path(r["file"]).name == r["file"],
            "stage shape, position or type",
        )
        info[name] = r
    return info


def check_payloads(blobs):
    need(struct.unpack("<4i", blobs["ffn_moe_topk"]) == IDS, "ordered logical ranks")
    need(struct.unpack("<4i", blobs["ffn_moe_topk_stream"]) == SLOTS, "ordered capture slots")
    for name, data in blobs.items():
        need(len(data) == 4 * math.prod(SHAPES[name]), "stage size")
        if "topk" not in name:
            need(
                all(math.isfinite(x) for (x,) in struct.iter_unpack("<f", data)), "nonfinite stage"
            )


def bindings(data):
    selected = [r for r in table(data) if r["phase"] == "decode0" and r["layer"] == "0"]
    result = {}
    for r in selected:
        who, slot, gen, tensor, n = map(
            int, [r[k] for k in ("logical", "slot", "generation", "tensor", "bytes")]
        )
        need(
            r["status"] == "EQUAL"
            and r["wave"] == "0"
            and who in IDS
            and SLOTS[IDS.index(who)] == slot
            and gen > 0
            and 0 <= tensor < 6
            and n == (schema["SLAB"] if tensor < 3 else schema["BIAS"]),
            "consumer proof, slot or size",
        )
        key = (who, tensor)
        need(key not in result, "duplicate consumer proof")
        result[key] = gen
    need(
        len(result) == 24 and all(len({result[e, k] for k in range(6)}) == 1 for e in IDS),
        "incomplete consumer proof",
    )
    return result


def compare_bytes(reference, candidate, name):
    need(
        len(reference) == len(candidate) == 4 * math.prod(SHAPES[name]) and reference == candidate,
        "C270 vs C127 bits: " + name,
    )


def stage_bundle(results, historical, out):
    prefix = "results/" + C270 + "/raw/c270-r0.capture/"
    tree = sealed(results / C270 / "raw-manifest.json", schema["REFS"]["C270"])
    files = {r["path"][len(prefix) :]: r for r in tree["files"] if r["path"].startswith(prefix)}
    new = results / C270 / "raw/c270-r0.capture"

    def get(name):
        r = files[name]
        return read(new / name, r["sha256"], r["size"])

    old_meta = select_stages(table((historical / "index.tsv").read_bytes()))
    new_meta = select_stages(table(get("index.tsv")))
    blobs = {}
    for name, row in new_meta.items():
        previous = old_meta[name]
        need(
            all(
                row[k] == previous[k]
                for k in ("first_abs", "chunk", "state_tokens", "ne", "nb", "bytes", "type")
            ),
            "C270 vs C127 shape",
        )
        data = get(row["file"])
        compare_bytes((historical / previous["file"]).read_bytes(), data, name)
        blobs[name] = data
    check_payloads(blobs)
    proof = bindings(get("byte_checks.tsv"))
    old_proof = bindings((historical / "byte_checks.tsv").read_bytes())
    need(proof == old_proof, "C270/C127 selected generation witnesses")
    hashes = {name: write(out / (name + ".bin"), data) for name, data in blobs.items()}
    return hashes, proof


def index_rows(index, proof):
    need(
        index["pack_bytes"] == 61_096_329_216
        and index["alignment"] == 4096
        and index["weight_window"] == schema["WINDOW"]
        and index["stride"] == schema["STRIDE"]
        and index["model_sha256_previous_verified"] == schema["MODEL"]
        and len(index["experts"]) == 4608,
        "integral index",
    )
    rows = []
    for rank, e in enumerate(IDS):
        r = index["experts"][e]
        off = r["pack_offset"]
        need(
            (r["layer"], r["expert"], r["tier"], off) == (0, e, "CPU", e * schema["STRIDE"])
            and len(r["components"]) == 6,
            "rank to record",
        )
        comps = []
        for i, c in enumerate(r["components"]):
            bias = i >= 3
            n = schema["BIAS" if bias else "SLAB"]
            rel = (schema["WINDOW"] if bias else 0) + (i % 3) * n
            need(
                (c["name"], c["type"], c["size_bytes"], c["packed_relative_offset"])
                == (
                    "blk.0.ffn_" + ROLES[i % 3] + "_exps." + ("bias" if bias else "weight"),
                    "f32" if bias else "mxfp4",
                    n,
                    rel,
                )
                and rel + n <= schema["STRIDE"]
                and 0 <= c["source_offset"] <= schema["MODEL_SIZE"] - n
                and re.fullmatch("[0-9a-f]{64}", c["sha256"]) is not None,
                "indexed role/offset/hash",
            )
            comps.append(dict(**c, pack_absolute_offset=off + rel, capture_tensor=C127_INDEX[i]))
        rows.append(
            dict(
                rank=rank,
                expert=e,
                capture_slot=SLOTS[rank],
                capture_generation=proof[e, 0],
                record_offset=off,
                record_bytes=schema["STRIDE"],
                components=comps,
            )
        )
    return rows


def prepare(a):
    results, root = a.lab / "results", a.manifest_dir
    cap, prior = resident(results)
    hashes, proof = stage_bundle(results, cap, a.new_output_dir)
    policy = run_path(QUAL / "packed_real_layer/policy/profile.py")
    meta = sealed(root / "receipt.json", DROOT)
    runtime = sealed(root / "expert-store-runtime.json", policy["MANIFEST"])
    idx = sealed(root / "integral-index.json", policy["INDEX"])
    original = sealed(results / schema["C290"], schema["INDEX"])
    pack = Path(meta["pack_path"])
    need(
        meta["status"] == "PASS_DERIVED_C290_NVME_METADATA"
        and meta["pack_placement_sha256"] == PLACEMENT
        and meta["original_index_sha256"] == schema["INDEX"]
        and meta["model_sha256"] == schema["MODEL"]
        and meta["index_sha256"] == runtime["index_sha256"] == policy["INDEX"]
        and meta["manifest_sha256"] == policy["MANIFEST"]
        and runtime["canonical_model_sha256"] == schema["MODEL"]
        and meta["pack_sha256"]
        == idx["pack_sha256_write_stream"]
        == original["pack_sha256_write_stream"]
        == policy["PACK"]
        and Path(runtime["index_path"]) == root / "integral-index.json"
        and pack == pack.resolve(strict=True) == Path(idx["pack_path"])
        and policy["fd_stat"](pack.stat()) == runtime["pack_stat"] == meta["pack_stat"]
        and all(idx["experts"][i] == original["experts"][i] for i in IDS),
        "relocation or integral pack identity",
    )
    recipe = index_rows(idx, proof)
    previous = sealed(a.tile_input / "prepare.json", PREP)
    router = {name: previous["file_sha256"][name] for name in ("router.weight", "router.bias")}
    # The consuming process must authenticate both router files when it opens them.
    plan = dict(
        records=recipe,
        pack_stat=meta["pack_stat"],
        pack_sha256=policy["PACK"],
        row_file_sha256=hashes,
        router_files_sha256=router,
        logical_order=list(IDS),
        position=189,
        layer=0,
        rows=1,
    )
    digest = write(
        a.new_output_dir / "plan.json", (json.dumps(plan, sort_keys=True, indent=2) + "\n").encode()
    )
    return dict(
        status="PASS_REUSED_C127_CPU0_DECODE0_GOLD",
        logical_ranks=list(IDS),
        c270_slots=list(SLOTS),
        c270_generations=[proof[e, 0] for e in IDS],
        c127=prior,
        c270_manifest_sha256=schema["REFS"]["C270"],
        placed_pack_receipt_sha256=PLACEMENT,
        derived_receipt_sha256=DROOT,
        logical_record_count=4,
        selected_weights=12,
        selected_biases=12,
        historical_consumer_checks=24,
        row_files_sha256=hashes,
        staged_rows_bytes=sum(4 * math.prod(shape) for shape in SHAPES.values()),
        gold_values=2880,
        gold_bytes=11520,
        plan_sha256=digest,
        planned_record_reads_bytes=4 * schema["STRIDE"],
        prospective_mutant="exchange_gate_backings_for_first_two_logical_ranks",
        pack_reads=0,
        model_reads=0,
        forwards=0,
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    for k in ("lab", "manifest-dir", "tile-input", "new-output-dir"):
        cli.add_argument("--" + k, type=Path, required=True)
    a = cli.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    try:
        signal.alarm(120)
        resource.setrlimit(resource.RLIMIT_AS, (512 << 20, 512 << 20))
        git = ["git", "-C", str(REPO), "-c", "core.preloadIndex=false", "-c", "index.threads=1"]
        need(not subprocess.check_output([*git, "status", "--porcelain"]), "dirty code")
        result = prepare(a)
        result.update(
            program_sha256=sha(Path(__file__)),
            protocol_sha256=sha(HERE / "protocol.md"),
            commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
        )
    except Exception as exc:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
