"""Join independent, measured operator outputs at their exact byte boundaries."""

import argparse
import hashlib
import json
import math
import operator
import os
import struct
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
CPU = "3ef107129e6d4c7afb755ac5836c9099b37a37f3eb3ab87f25fed3e9ba28dd53"
PRIMARY = "66d7f6f83252ffa0290ac1c712a5a2fc09bd9c27a08ed81796a4963a79fd6449"
ACT = "1c7fa886160b01c8f2eb0ce883faf5db666fbc00a04586c694d63ef520df4cd6"
MANIFEST = "cd4c0665c5485268cddfc7dba576b1cf490222c120cf34f72d555a6cbccbc5b9"
GOLD = "6bc70d200ac08db00f6c3fa34098bd660d2ba4bc4c02368de319cbadf6167333"
K = 2880
ROW = K * 4
F32 = struct.Struct("<f")


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sealed(path, digest, n=None):
    need(path.is_file() and not path.is_symlink(), "missing or linked " + path.name)
    if n is not None:
        need(path.stat().st_size == n, "size " + path.name)
    b = path.read_bytes()
    need(sha(b) == digest, "digest " + path.name)
    return b


def receipt(folder, digest):
    return json.loads(sealed(folder / "receipt.json", digest))


def module(name, digest):
    file = HERE.parent / name
    sealed(file, digest)
    return run_path(file)


def vals(b):
    need(len(b) % 4 == 0, "F32 width")
    v = [x[0] for x in struct.iter_unpack("<f", b)]
    need(all(map(math.isfinite, v)), "nonfinite operand")
    return v


def apply(a, b, operation):
    need(len(a) == len(b), "elementwise geometry")
    return b"".join(F32.pack(operation(x, y)) for x, y in zip(vals(a), vals(b), strict=True))


def compare(a, b):
    pairs = list(zip(vals(a), vals(b), strict=True))
    changed = [i for i in range(len(pairs)) if a[4 * i : 4 * i + 4] != b[4 * i : 4 * i + 4]]
    return dict(
        words=len(pairs),
        different=len(changed),
        first=next(iter(changed), None),
        max_abs=max((abs(x - y) for x, y in pairs), default=0.0),
        sha256=sha(a),
        gold_sha256=sha(b),
    )


def join_down(down, bias, mix, weighted):
    need(len(mix) == 16 and len(weighted) == 4 * len(down) and down, "four rank geometry")
    down_biased = apply(down, bias, operator.add)
    selected = apply(down_biased, mix[:4] * (len(down) // 4), operator.mul)
    acc = selected
    for r in range(1, 4):
        acc = apply(acc, weighted[r * len(down) : (r + 1) * len(down)], operator.add)
    return down_biased, selected, acc


def fd_identity(st):
    return dict(
        dev=st.st_dev,
        inode=st.st_ino,
        size_bytes=st.st_size,
        mtime_ns=st.st_mtime_ns,
        ctime_ns=st.st_ctime_ns,
    )


def bias_descriptors(idx):
    roles = ("gate", "down", "up")
    need(
        (
            idx["alignment"],
            idx["weight_window"],
            idx["stride"],
            idx["pack_bytes"],
            len(idx["experts"]),
        )
        == (4096, 13_221_888, 13_258_752, 61_096_329_216, 4608),
        "C290 geometry",
    )
    row = idx["experts"][28]
    need(
        (row["expert"], row["layer"], row["tier"], row["pack_offset"], len(row["components"]))
        == (28, 0, "CPU", 371245056, 6),
        "logical record",
    )
    descriptors = {}
    for i, (role, d) in enumerate(zip(roles, row["components"][3:], strict=True)):
        offset = idx["weight_window"] + i * ROW
        need(
            (d["type"], d["name"], d["size_bytes"], d["packed_relative_offset"])
            == ("f32", f"blk.0.ffn_{role}_exps.bias", ROW, offset),
            "role or offset",
        )
        descriptors[role] = dict(offset=row["pack_offset"] + offset, bytes=ROW, sha256=d["sha256"])
    return descriptors


def read_biases(folder, log):
    meta = receipt(folder, MANIFEST)
    idx = json.loads(sealed(folder / "integral-index.json", meta["index_sha256"]))
    need(
        meta["status"] == "PASS_DERIVED_C290_NVME_METADATA"
        and idx["pack_sha256_write_stream"] == meta["pack_sha256"]
        and idx["pack_path"] == meta["pack_path"],
        "pack placement",
    )
    desc = bias_descriptors(idx)
    out = {}
    pack = Path(meta["pack_path"])
    fd = os.open(pack, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        need(fd_identity(os.fstat(fd)) == meta["pack_stat"], "pack opened inode")
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_RANDOM)
        for role, d in desc.items():
            log.append(dict(role=role, **d, returned=0))
            out[role] = os.pread(fd, d["bytes"], d["offset"])
            log[-1]["returned"] = len(out[role])
            need(len(out[role]) == ROW and sha(out[role]) == d["sha256"], "pack bias " + role)
        need(
            fd_identity(os.fstat(fd)) == fd_identity(pack.stat()) == meta["pack_stat"], "pack after"
        )
    finally:
        os.close(fd)
    return out


def run(a, row):
    cpu, p, act, d = (
        receipt(path, pin)
        for path, pin in (
            (a.cpu_dir, CPU),
            (a.primary_dir, PRIMARY),
            (a.swiglu_dir, ACT),
            (a.down_dir, a.down_sha256),
        )
    )
    need(
        cpu["status"] == "PASS_CPU0_RANK_STAGES_REFERENCE"
        and p["cpu_sha256"] == CPU
        and p["result"]["decision"] == "GO_DENSE_GGML_PRIMARY_GATE_UP_ONLY"
        and act["cpu_receipt_sha256"] == CPU
        and act["result"]["decision"] == "EQUAL_EFFECTIVE_DOWN_OPERAND_ONLY",
        "predecessor evidence",
    )
    row.update(
        cpu_sha256=CPU,
        primary_sha256=PRIMARY,
        activation_sha256=ACT,
        down_sha256=a.down_sha256,
        derived_manifest_sha256=MANIFEST,
        pack_preads=[],
        dispatches_by_reviewer=0,
        model_forwards=0,
    )
    need(
        d["status"] == "MEASURED_RADV_RANK_DOWN"
        and d["primary_sha256"] == PRIMARY
        and d["swiglu_sha256"] == ACT
        and d["cpu_sha256"] == CPU
        and d["scope_after"] == p["scope_after"] == ["ActiveState=inactive", "SubState=dead"],
        "down authority or incomplete physical run",
    )

    folder = a.cpu_dir / "ALIAS/rank"
    cpu_mod = module(
        "rank_cpu/grade.py", "007ee67dad130131c6a7bb42e7a1f885222ab16293abb3087b8c2928fd79bad7"
    )
    ref = cpu_mod["verify_rank"](folder, cpu["arm"]["native"])
    need(ref == cpu["arm"]["rank"], "reopened rank witnesses")
    r = {
        s: sealed(folder / (s + ".f32"), ref["files_sha256"][s + ".f32"], 4 * ROW)
        for s in cpu_mod["STAGES"]
    }
    qgold = sealed(folder / "down-rank0.q8", ref["files_sha256"]["down-rank0.q8"], 3060)
    mix = sealed(folder / "mix.f32", ref["files_sha256"]["mix.f32"], 16)
    full = sealed(folder.parent / "native/decode.f32", GOLD, ROW)
    pre = {
        n: sealed(a.primary_dir / (n + ".f32"), p["files"][n + ".f32"], ROW)
        for n in ("e28-gate", "e28-up", "e24-gate")
    }
    edges = {
        f"primary_{name}": compare(pre[name], r[op][rank * ROW : (rank + 1) * ROW])
        for name, op, rank in (
            ("e28-gate", "gate", 0),
            ("e28-up", "up", 0),
            ("e24-gate", "gate", 1),
        )
    }
    bias = read_biases(a.manifest_dir, row["pack_preads"])
    biased = {op: apply(pre["e28-" + op], bias[op], operator.add) for op in ("gate", "up")}
    act_mod = module(
        "rank_activation/grade.py",
        "1802853558c49856017ae111cf46de6566f496e525e81cf03b85c30e4dc94258",
    )
    arith = module(
        "reference/arithmetic.py",
        "f69971181e20e326f1efcb6f070454180f5faa90baeac743152fe17650a87c53",
    )
    need(
        [j["name"] for j in act["jobs"]] == ["a0", "a1", "a2", "a3", "q8"], "physical segment order"
    )
    outputs, live_inputs = [], {"gate": [], "up": []}
    for i, j in enumerate(act["jobs"][:4]):
        inp = sealed(a.swiglu_dir / f"input-{i}.f32", j["input_sha256"], ROW)
        need(inp[ROW // 2 :] == bytes(ROW // 2), "packed activation input padding")
        live_inputs["gate"].append(inp[: ROW // 4])
        live_inputs["up"].append(inp[ROW // 4 : ROW // 2])
        outputs.append(
            sealed(a.swiglu_dir / j["name"] / "actual.bin", j["files"]["actual.bin"], 3312)
        )
    for op in ("gate", "up"):
        gold = r[op + "-biased"][:ROW]
        need(sha(gold) == act["inputs"][op + "-biased"], "activated rank")
        edges[op + "_biased_vs_cpu"] = compare(biased[op], gold)
        edges[op + "_biased_vs_dispatched"] = compare(biased[op], b"".join(live_inputs[op]))

    gpu_s = act_mod["assemble"](outputs)
    need(
        gpu_s == sealed(a.swiglu_dir / "swiglu.f32", act["swiglu_sha256"], ROW)
        and sha(gpu_s) == d["input_swiglu_f32_sha256"] == act["jobs"][4]["input_sha256"],
        "down input",
    )
    gpu_q = sealed(a.swiglu_dir / "q8/actual.bin", act["jobs"][4]["files"]["actual.bin"], 3312)
    qdown = sealed(a.down_dir / "actual.q8_1", d["files"]["actual.q8_1"], 3312)
    aval = act_mod["evaluate"](r["swiglu"][:ROW], qgold, gpu_s, gpu_q, arith)
    need(
        aval == act["result"]
        and aval["f32"]["changed_bits_words"] == 979
        and d["expected_q8_sha256"] == sha(gpu_q),
        "reproduced observed activation",
    )
    x4_count = sum(i != j for i, j in zip(qdown, gpu_q, strict=True))
    eff = act_mod["q_diff"](qgold, arith["from_x4"](qdown))
    down = sealed(a.down_dir / "e28-down.f32", d["files"]["e28-down.f32"], ROW)
    ctrl = sealed(a.down_dir / "e24-down.f32", d["files"]["e24-down.f32"], ROW)
    different = compare(ctrl, down)["different"]
    edges["down_before_bias"] = compare(down, r["down"][:ROW])
    need(
        different > 0
        and different == d["result"]["control_changed_words"]
        and x4_count == d["result"]["q8_different_bytes"]
        and edges["down_before_bias"]["different"] == d["result"]["differences"],
        "independent down or control count",
    )
    biased_down, contribution, ffn = join_down(down, bias["down"], mix, r["weighted"])
    for name, real, gold in (
        ("down_biased", biased_down, r["down-biased"][:ROW]),
        ("weighted_e28", contribution, r["weighted"][:ROW]),
        ("ordered_ffn", ffn, full),
    ):
        edges[name] = compare(real, gold)
    ok = x4_count == 0 and eff["same_input"] and all(x["different"] == 0 for x in edges.values())
    return dict(
        status=("GO_COMPOSED_E28_CONTRIBUTION_AND_FFN" if ok else "NO_GO_COMPOSED_E28"),
        coordinate_count=K,
        cpu_only_weighted_ranks=[1, 2, 3],
        cpu_rank_ids=ref["logical"],
        edges=edges,
        activation=aval,
        down_effective_vs_cpu=eff,
        q8_raw_different_bytes=x4_count,
        q8_raw_bytes=len(qdown),
        e24_same_rhs_control_changed_words=different,
        unchanged_cpu_weighted_sha256=ref["row_sha256"]["weighted"][1:],
        pread_requested_bytes=sum(x["bytes"] for x in row["pack_preads"]),
        pread_returned_bytes=sum(x["returned"] for x in row["pack_preads"]),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("cpu-dir", "primary-dir", "swiglu-dir", "down-dir", "manifest-dir", "new-output-dir"):
        p.add_argument("--" + n, type=Path, required=True)
    p.add_argument("--down-sha256", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    row = dict(
        program_sha256=sha(Path(__file__).read_bytes()),
        protocol_sha256=sha((HERE / "protocol.md").read_bytes()),
    )
    try:
        row.update(run(a, row))
    except Exception as exc:
        row.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    with (a.new_output_dir / "receipt.json").open("x") as file:
        print(json.dumps(row, sort_keys=True, indent=2, allow_nan=False), file=file)
    print(row["status"], row.get("reason", ""))
    return int(row["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
