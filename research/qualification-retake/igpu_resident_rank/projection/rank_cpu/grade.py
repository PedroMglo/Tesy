"""Verify the four C270 rank rows, router weighting and ordered F32 reduction."""

import hashlib
import json
import math
import os
import struct
from pathlib import Path
from runpy import run_path

K = 2880
RANKS = 4
ROW = K * 4
STAGES = ("gate", "up", "gate-biased", "up-biased", "swiglu", "down", "down-biased", "weighted")
F32 = struct.Struct("<f")
LOGICAL = [28, 24, 8, 16]
PHYSICAL = [3, 14, 6, 35]
GENERATIONS = [6, 6, 5, 4]
GATE = "756c8384a4cda89c62040a81d3e45dd06e0707121dcbadecc73d45ecec0e1db3"
GOLD = "6bc70d200ac08db00f6c3fa34098bd660d2ba4bc4c02368de319cbadf6167333"
MIX = "2144b1ce76f2161a0ae725f6341c7811c33c5c4ae16366620736103704feb18d"
ARITHMETIC = "f69971181e20e326f1efcb6f070454180f5faa90baeac743152fe17650a87c53"
CPU = "9aabce5751c5d7ca19b50e4cabb1fcf484c1581d275141dae8aba8ed33060313"
BASE = "6e27d9ecb86e4747177189d2d2f6390280a2ee1000221ad68a0404023ea72539"


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path, size):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size == size, path.name)
    data = path.read_bytes()
    require(len(data) == size, path.name)
    return data


def f32(value):
    return F32.unpack(F32.pack(value))[0]


def floats(data):
    values = [v for (v,) in struct.iter_unpack("<f", data)]
    require(all(map(math.isfinite, values)), "nonfinite rank observation")
    return values


def compare_stages(data, final, quantize):
    """Independent of native output digests. Inputs use the original rank-major layout."""
    require(set(data) == {*(s + ".f32" for s in STAGES), "mix.f32", "down-rank0.q8"}, "rank files")
    by_stage = {}
    for stage in STAGES:
        raw = data[stage + ".f32"]
        require(len(raw) == ROW * RANKS, stage + " shape")
        floats(raw)
        by_stage[stage] = [sha(raw[r * ROW : (r + 1) * ROW]) for r in range(RANKS)]
    require(len(data["mix.f32"]) == RANKS * 4 and len(final) == ROW, "mix/final shape")
    mix = floats(data["mix.f32"])
    floats(final)
    down = floats(data["down-biased.f32"])
    products = bytearray()
    for rank, weight in enumerate(mix):
        for value in down[rank * K : (rank + 1) * K]:
            products.extend(F32.pack(value * weight))
    require(products == data["weighted.f32"], "rank-specific router product")
    contributions = floats(products)
    recovered = bytearray()
    for i in range(K):
        v = contributions[i]
        for rank in range(1, RANKS):
            v = f32(v + contributions[rank * K + i])
        recovered.extend(F32.pack(v))
    require(recovered == final, "left-associated FFN")
    q = quantize(data["swiglu.f32"][:ROW])
    require(len(q) == 3060 and q == data["down-rank0.q8"], "down rank zero Q8_0")
    return by_stage


def check_fields(proof, expected):
    for key, value in expected.items():
        observed = proof.get(key)
        require(type(observed) is type(value) and observed == value, "native field " + key)
        if isinstance(value, list):
            require(all(type(item) is int for item in observed), "non-integer " + key)


def verify_rank(folder: Path, prior_row: dict) -> dict:
    folder = Path(folder)
    names = {**{f"{s}.f32": ROW * RANKS for s in STAGES}, "mix.f32": 16, "down-rank0.q8": 3060}
    require(folder.is_dir() and not folder.is_symlink(), "rank output directory")
    require({p.name for p in folder.iterdir()} == {"rank.json", *names}, "rank output census")
    header = folder / "rank.json"
    require(
        header.is_file() and not header.is_symlink() and header.stat().st_size <= 32768,
        "rank header",
    )
    proof = json.loads(header.read_bytes())
    check_fields(
        prior_row,
        dict(
            status="PASS_C291_CPU0_DECODE_HANDOFF",
            mode="ALIAS",
            finite=True,
            unequal=0,
            mmid_nodes=3,
            add_id_nodes=3,
            equal_components=24,
            hits=3,
            misses=1,
            joined_workers=4,
        ),
    )
    check_fields(
        proof,
        dict(
            status="PASS_CPU0_RANK_STAGES_CAPTURE",
            shape=[K, RANKS, 1, 1],
            logical=LOGICAL,
            physical=PHYSICAL,
            generations=GENERATIONS,
            mmid_edges=3,
            bias_edges=3,
            glu_edges=1,
            weighted_edges=1,
            reduction_views=4,
            reduction_adds=3,
            biased_values_checked=34560,
        ),
    )
    for role, digest in (("cpu", CPU), ("base", BASE)):
        path = Path(proof["provider_" + role])
        require(
            path.is_absolute() and path.samefile(prior_row["providers"][role]), role + " identity"
        )
        require(sha(path.read_bytes()) == digest, role + " digest")
    blobs = {name: read(folder / name, size) for name, size in names.items()}
    digests = {name: sha(data) for name, data in blobs.items()}
    require(digests == proof.get("files_sha256"), "native file digests")
    final = read(folder.parent / "native" / "decode.f32", ROW)
    require(sha(final) == GOLD and digests["mix.f32"] == MIX, "C127 FFN and C270 mix")
    require(sha(blobs["gate.f32"][:ROW]) == GATE, "previous e28 pre-bias gate")
    arithmetic = Path(__file__).resolve().parent.parent / "reference" / "arithmetic.py"
    require(sha(arithmetic.read_bytes()) == ARITHMETIC, "C269 quantizer replica")
    rows = compare_stages(blobs, final, run_path(os.fspath(arithmetic))["quantize"])
    return dict(
        status="PASS_CPU0_RANK_STAGES_REVIEW",
        rank_sha256=sha(header.read_bytes()),
        logical=LOGICAL,
        physical=PHYSICAL,
        generations=GENERATIONS,
        files_sha256=digests,
        row_sha256=rows,
        ffn_sha256=GOLD,
        quantizer_source_sha256=ARITHMETIC,
        f32_router_products=K * RANKS,
        f32_ordered_sums=K,
        down_rank0_q8_bytes=3060,
        native_bias_values_checked=34560,
        expected_provider_sha256={"cpu": CPU, "base": BASE},
    )
