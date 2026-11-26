"""Prepare a tiny plan from the sealed C283 tensor table, using only stat on the model."""

import argparse
import hashlib
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
META = run_path(str(HERE.parents[1] / "verify.py"))
PLACEMENT = "50a35a1e5c3fde78066d1378e13dfeb89867d9970528135ff3294c6aa5bd1bf7"
MODEL = "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"
PRIOR = "8343243f506088714e3c16e83d834e82c85faa30878010a8837815f678c90c37"
STAT = (56, 40127919, 63387346208, 1795562532015886541, 1795562532015886541)
ORIGINAL = Path("/home/pmglo/models/tesy-gpt-oss-120b-nvme/gpt-oss-120b-MXFP4.gguf")
DTYPE = {"f32": 0, "q8_0": 8, "mxfp4": 39}
MIB = 1 << 20
WIDTH = 4406400
TUPLE = 3 * WIDTH
BUDGET = 3644 * MIB
need = META["need"]
sha = META["sha"]


def plan_bytes(raw, path, stat):
    META["layer_geometry"](raw)
    need(path == ORIGINAL and tuple(stat) == STAT, "NVMe placement identity")
    header = "MODEL " + str(path) + " " + " ".join(map(str, stat))
    rows = []
    for line in raw.splitlines()[1:]:
        t = json.loads(line)
        shape = t["shape"]
        need(1 <= len(shape) <= 4 and all(type(i) is int and i > 0 for i in shape), "tensor shape")
        rows.append(
            [
                t["name"],
                t["data_offset"],
                t["n_bytes"],
                DTYPE[t["tensor_type"]],
                *(shape + [1] * (4 - len(shape))),
            ]
        )
    return ("\n".join([header] + ["T " + " ".join(map(str, row)) for row in rows]) + "\n").encode()


def produce(a):
    raw = a.inventory.read_bytes()
    need(
        hashlib.sha256(raw).hexdigest() == META["INVENTORY"] and sha(a.placement) == PLACEMENT,
        "inventory or placement digest",
    )
    p = json.loads(a.placement.read_bytes())
    need(
        p["status"] == "PASS_NVME_MODEL_PLACEMENT"
        and Path(p["working_copy"]) == ORIGINAL
        and p["destination_transport"] == "nvme"
        and p["source_sha256"] == MODEL
        and p["destination_direct_reread"]["size_bytes"] == STAT[2]
        and p["destination_direct_reread"]["sha256"] == MODEL,
        "direct readback",
    )
    st = ORIGINAL.stat()
    actual = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    need(ORIGINAL.resolve(strict=True) == ORIGINAL, "canonical model")
    plan = plan_bytes(raw, ORIGINAL, actual)
    (a.new_output_dir / "plan.tsv").write_bytes(plan)
    return dict(
        status="PASS_IK_CAPACITY_INPUT_IDENTITY",
        plan_sha256=hashlib.sha256(plan).hexdigest(),
        model=str(ORIGINAL),
        model_stat=list(actual),
        model_sha256=MODEL,
        placement_sha256=PLACEMENT,
        inventory_sha256=META["INVENTORY"],
        model_stat_receipt_sha256=PRIOR,
        tensors=687,
        matrix_tensors=108,
        bias_tensors=108,
        requested_bytes=BUDGET,
        slots=BUDGET // TUPLE - 1,
        guard_slots=1,
        tuple_bytes=TUPLE,
        bytes_read_from_model=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("inventory", "placement", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        r = produce(a)
    except Exception as exc:
        r = dict(status="FAIL_PRESERVED", reason=str(exc))
    (a.new_output_dir / "receipt.json").write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
    print(r["status"])
    return r["status"] == "FAIL_PRESERVED"


if __name__ == "__main__":
    raise SystemExit(main())
