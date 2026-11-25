"""Selected C292 fidelity on a closed C127/C270 capture, with private bytes kept local."""

import csv
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[1]
REPO = QUAL.parents[1]
TOOLS = REPO / "tools"
sys.path.insert(0, str(TOOLS))
import expert_store_numeric_gate as strong  # noqa: E402
from c70_full_boundary_gate import _index, _values  # noqa: E402
from c94_session_wave_8k_reference import tree_digest  # noqa: E402

R0 = "1f332ad437d90c24adf3b88b87ddf0dac8e13b7e87e818d93461ffd281c801b6"
SELECTED = "786b6911b7d56a78fc59a6c23d67f748e8dad8c6dd08da6c8608fd80b37681f3"
SEAL = "29795e9d68452efb6e0dea1df9e873b27fcf1011d36b899abd52bfdd91ce2a8e"
SOURCE = {
    "block_layer_reuse_gate.py": "2b47079f3eab3975e78da12f9fc9a0c40d0ced417375d91ab4e42d81e8e39017",
    "expert_store_numeric_gate.py": "3b420b6e8f4b33116e0f4c7fb6697c4db6c4457b39866f01ee85e5ec66310427",  # noqa: E501
    "c210_witness_gate.py": "7af2dc3e86ec3591a7cd45ba92a8e2579ad56a000b62b84383bdf8ccb6b627d0",
    "c70_full_boundary_gate.py": "c3b672542f15a4bce416a5f76c922df45c1e808512f6560f234bdf47bfe25072",
    "c7_boundary_gate.py": "0c733a8553be108ba6bed20f5cc67a8788d28b13b27e99d6eaf10080b9d893be",
}
VOCAB = 201088
LABELS = ("prefill_final", "decode0", "decode1", "decode7", "decode31")
PHASES = ("prefill0", "prefill128", *LABELS)
CENSUS = {
    "capture_tensors": 3255,
    "bytes": 84291920,
    "checked_slices": 996,
    "checked_bytes": 2200124160,
    "sentinel_pairs": 896,
    "prompt_ids": 189,
    "continuation_ids": 43,
    "masked_states": 2,
}
WITNESS = {
    "status": "PASS_PROSPECTIVE_WITNESS",
    "components": 996,
    "combinations": 166,
    "coverage": [
        ["decode0", 0],
        ["decode0", 25],
        ["decode0", 29],
        ["decode0", 35],
        ["prefill0", 0],
        ["prefill0", 25],
        ["prefill0", 29],
    ],
}
C127 = {
    "status": "PASS_PRIVATE_R0_SELECTED_BRIDGE",
    "core_payloads": 1500,
    "full_logits": 5,
    "prospective_witness": WITNESS,
}


class FidelityMismatch(ValueError):
    """Two authenticated, usable outputs differ under the frozen contract."""


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path, expected_digest):
    need(digest(path) == expected_digest, "unrecognized " + path.name)
    return json.loads(path.read_bytes())


def anchors():
    for name, expected in SOURCE.items():
        need(digest(TOOLS / name) == expected, "historical gate changed: " + name)
    return read(QUAL / "nvme_r0_gate/inputs/receipt.json", SEAL)


def regular_files(root):
    files = list(root.iterdir())
    need(
        not root.is_symlink() and all(p.is_file() and not p.is_symlink() for p in files),
        "capture contains an indirect or nonregular file",
    )
    return files


def logits(root):
    result = {}
    for phase in LABELS:
        p = root / (phase + ".logits.f32")
        need(p.stat().st_size == 4 * VOCAB, "incomplete full logit vector")
        result[phase] = digest(p)
    return result


def reference(r0_dir: Path) -> Path:
    """Bind the actual post-driver E20 output tree, including every ancillary file."""
    sealed = anchors()
    r = read(r0_dir / "receipt.json", R0)
    selected = read(r0_dir / "selected.json", SELECTED)
    need(
        r["status"] == "PASS_SELECTED_C269_BRIDGE"
        and r["envelope"] == "E20_R0"
        and r["model_launch_receipts"] == 1
        and r["selected_sha256"] == SELECTED
        and r["numerical_gate"] == selected == C127,
        "independent C270 numerical gate",
    )
    numeric = read(r0_dir / "protocol.json", r["protocol_sha256"])
    unit = numeric["execution_scope_unit"].removesuffix(".scope")
    need(unit == "tesy-c270-driver-20261125-r01", "C270 scope binding")
    root = r0_dir / "raw" / (unit + ".capture")
    regular_files(root)
    # This C270 reproduced even the complete name/size/content hash of the C127 ON tree.
    need(
        tree_digest(root) == numeric["pinned"]["gold"] == sealed["gold"]
        and logits(root)
        == numeric["pinned"]["gold_full_logits_sha256"]
        == sealed["gold_full_logits_sha256"],
        "independent C270 output tree changed",
    )
    return root


def stdout_counts(text):
    lines = text.splitlines()
    expected = ["C80_CONTEXT_READY ngl=12 case=log_medium ctx=8192 preload=on kv_unified=1"]
    expected += [
        f"captured={phase} tensors={count}"
        for phase, count in zip(LABELS, (2247, 2499, 2751, 3003, 3255), strict=True)
    ]
    expected.append(" ".join(f"{k}={v}" for k, v in CENSUS.items()))
    need(lines == expected, "C292 native phase/counter transcript differs")
    return dict(CENSUS)


def sentinel_scope(row):
    # The native callback increments this counter after the byte_check early return.
    return (
        row["phase"] in ("prefill0", "decode0")
        and int(row["layer"]) in (0, 25, 29, 35)
        and row["name"] in ("ffn_moe_wave_ids", "ffn_moe_topk_stream")
    )


def evidence(root):
    rows = _index(root)
    counts = sum(_values(root, r).count(-1) for r in rows if sentinel_scope(r))
    with (root / "byte_checks.tsv").open(newline="") as f:
        witness = list(csv.DictReader(f, delimiter="\t"))
    need(
        len(rows) == CENSUS["capture_tensors"]
        and sum(int(r["bytes"]) for r in rows) == CENSUS["bytes"]
        and len(witness) == CENSUS["checked_slices"]
        and sum(int(r["bytes"]) for r in witness) == CENSUS["checked_bytes"]
        and counts == CENSUS["sentinel_pairs"]
        and tuple((root / "phases.txt").read_text().splitlines()) == PHASES,
        "C292 tensor/witness/sentinel accounting differs",
    )
    return {
        "capture": tree_digest(root),
        "logit_sha256": logits(root),
        "index_sha256": digest(root / "index.tsv"),
        "consumer_rows_sha256": digest(root / "byte_checks.tsv"),
        "masked_sha256": digest(root / "masked.tsv"),
        "vocab": VOCAB,
        "phases": list(PHASES),
        "logit_phases": list(LABELS),
        "sentinel_pairs": counts,
    }


def compare(capture, other):
    need(not capture.samefile(other), "comparison with same capture")
    regular_files(capture)
    regular_files(other)
    try:
        result = strong.compare(capture, other)
    except ValueError as e:
        # The historical validator distinguishes bad capture coverage from a discrepancy
        # found after qualified(other) and qualified(capture) both succeeded.
        if str(e).startswith("same-profile transport payload differs:"):
            raise FidelityMismatch(str(e)) from e
        raise
    need(
        result["status"] == "PASS_SELECTED_R0_EXPERT_STORE_NUMERICAL_BRIDGE"
        and result["core_payloads"] == 1500
        and result["numeric_states"] == 250
        and result["masked_states"] == 2
        and result["full_logits"] == 5
        and json.loads(json.dumps(result["prospective_witness"])) == WITNESS,
        "C292 comparator coverage differs",
    )
    a = evidence(capture)
    need(a["logit_sha256"] == logits(other), "C292 full-logit digests disagree with gate")
    return {
        k: result[k]
        for k in ("status", "core_payloads", "numeric_states", "masked_states", "full_logits")
    } | {
        "prospective_witness": WITNESS,
        "reference_index_sha256": result["reference_index_sha256"],
        **a,
    }


def check_arm(capture: Path, raw_stdout: Path, r0_capture: Path, c127_grade: dict) -> dict:
    sealed = anchors()
    need(c127_grade == C127, "missing independent C127 bridge")
    counts = stdout_counts(raw_stdout.read_text())
    # Accept a relocated reference, but never reinterpret a caller-supplied path as gold.
    regular_files(r0_capture)
    need(tree_digest(r0_capture) == sealed["gold"], "unsealed independent reference")
    result = compare(capture, r0_capture)
    return {
        "status": "PASS_C292_ARM_NUMERICS",
        "c127": C127,
        "c292": result,
        "native": counts,
        "stdout_sha256": digest(raw_stdout),
        "reference_receipt_sha256": R0,
    }


def check_pair(off_capture: Path, on_capture: Path) -> dict:
    anchors()
    result = compare(on_capture, off_capture)
    return {
        "status": "PASS_C292_OFF_ON_SELECTED",
        "c292": result,
        "off_capture": tree_digest(off_capture),
        "on_capture": result["capture"],
    }
