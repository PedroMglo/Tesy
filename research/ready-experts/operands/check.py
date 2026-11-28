"""Measure exact operand sparsity and price its best possible weight layout in bytes."""

import argparse
import ctypes
import hashlib
import json
import math
import struct
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[1] / "qualification-retake"
ARITH = run_path(QUAL / "igpu_resident_rank/projection/reference/arithmetic.py")
METHOD = "7f6e15e83b104719c05bf697a3d3957b3d7dffec066b749c888bb9219073541b"
MANIFESTS = {
    86: "cd75a342a6c3c6cd55fc8d3f823531fce10c49205c8e4628aabf0bb1fec87819",
    110: "ea5e194d093797754284c694d7f9de6bd63fb59d651fbfab94eee6fc9ebfb92b",
}
LIBS = {
    "libggml-base.so.0.15.3": "6e27d9ecb86e4747177189d2d2f6390280a2ee1000221ad68a0404023ea72539",
    "libggml-cpu.so.0.15.3": "9aabce5751c5d7ca19b50e4cabb1fcf484c1581d275141dae8aba8ed33060313",
}
N = 2880
ROW = 17 * (N // 32)
PAYLOAD = ROW * N * 3
WINDOW = 13_221_888
PAGE = 4096
BOUNDARY = (
    "tesy-l25-inputs-physical-20261125-r01/ON/raw/tesy-l25-inputs-20261125-r01-on.capture/boundary"
)
RANK = "tesy-e28-rank-cpu-physical-20261125-r01/ALIAS/rank"
REQUIRED_PPM = 268818


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Archive:
    def __init__(self, root, part):
        self.path = root / f"part-{part}"
        raw = (self.path / "manifest.json").read_bytes()
        need(sha(raw) == MANIFESTS[part], "archive manifest")
        self.files = json.loads(raw)["files"]

    def read(self, key):
        f = self.files[key]
        path = self.path / key
        raw = path.read_bytes()
        need(
            not path.is_symlink() and len(raw) == f["bytes"] and sha(raw) == f["sha256"],
            "input " + key,
        )
        return raw


class Quantizer:
    def __init__(self, libdir):
        files = [(libdir / name).resolve(strict=True) for name in LIBS]
        for path, digest in zip(files, LIBS.values(), strict=True):
            need(sha(path.read_bytes()) == digest, "C269 library digest")
        self.base, self.cpu = [ctypes.CDLL(str(p), mode=ctypes.RTLD_GLOBAL) for p in files]
        mappings = [line.split()[-1] for line in Path("/proc/self/maps").read_text().splitlines()]
        for path in files:
            loaded = {Path(name).resolve() for name in mappings if Path(name).name == path.name}
            need(loaded == {path}, "ambiguous C269 provider")
        self.call = self.cpu.quantize_row_q8_0
        self.call.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64]
        self.call.restype = None
        self.digest = hashlib.sha256()
        self.rows = 0

    def row(self, raw, where):
        need(
            len(raw) == N * 4 and all(math.isfinite(v) for (v,) in struct.iter_unpack("<f", raw)),
            "non-finite or malformed source at " + where,
        )
        dest = ctypes.create_string_buffer(N // 32 * 34)
        self.call(ctypes.create_string_buffer(raw), dest, N)
        native = dest.raw
        other = ARITH["quantize"](raw)
        if native != other:
            i = next(n for n, (a, b) in enumerate(zip(native, other, strict=True)) if a != b)
            raise ValueError(f"Q8_0 at {where} byte {i}: native={native[i]} independent={other[i]}")
        self.rows += 1
        self.digest.update(native)
        return native


@dataclass
class WeightRow:
    inactive: int
    empty_blocks: int
    needed_bytes: bytes

    @property
    def saved_nibbles(self):
        # Each omitted exponent buys a byte in addition to its codes.
        return self.inactive + 2 * self.empty_blocks


def weight_mask(q8):
    mask = bytearray()
    inactive = empty_blocks = 0
    for scale, *codes in struct.iter_unpack("<e32b", q8):
        need(math.isfinite(scale) and scale >= 0, "invalid effective scale")
        used = [bool(scale and x) for x in codes]
        active = sum(used)
        inactive += 32 - active
        empty_blocks += not active
        mask.append(bool(active))
        mask.extend(used[i] or used[i + 16] for i in range(16))
    return WeightRow(inactive, empty_blocks, bytes(mask))


def needed_between(pattern, start, n):
    if not n:
        return False
    if n >= len(pattern):
        return 1 in pattern
    i = start % len(pattern)
    return 1 in pattern[i : i + n] or (
        i + n > len(pattern) and 1 in pattern[: i + n - len(pattern)]
    )


def saved_pages(roles, rows, page):
    row_bytes = len(roles[0])
    need(row_bytes > 0 and all(len(r) == row_bytes for r in roles), "row width")
    extent = rows * row_bytes
    total = len(roles) * extent
    spared = 0
    for start in range(0, total, page):
        current, end = start, min(start + page, total)
        while current < end:
            role, offset = divmod(current, extent)
            take = min(end - current, extent - offset)
            if needed_between(roles[role], offset, take):
                break
            current += take
        else:
            spared += 1
    return spared


def price(x, down):
    """Two projections use x. Grant the oracle all of the down mask before they run."""
    partial = N * (2 * x.saved_nibbles + down.saved_nibbles)
    # Only retained gate/up bytes can be saved a second way by the oracle.
    remaining_gate_row = 2 * ROW - x.saved_nibbles
    grant = 2 * down.inactive * remaining_gate_row
    return Counter(
        records=1,
        payload_bytes=PAYLOAD,
        input_inactive_coordinates=x.inactive,
        down_inactive_coordinates=down.inactive,
        effective_inactive_blocks=2 * x.empty_blocks + down.empty_blocks,
        whole_block_saved_bytes=N * 17 * (2 * x.empty_blocks + down.empty_blocks),
        paired_nibble_saved_bytes=N * (2 * x.needed_bytes.count(0) + down.needed_bytes.count(0)),
        causal_saved_half_bytes=partial,
        oracle_saved_half_bytes=partial + grant,
        pack_saved_pages=saved_pages([x.needed_bytes, down.needed_bytes, x.needed_bytes], N, PAGE),
    )


def run(a):
    need(sha((HERE / "protocol.md").read_bytes()) == METHOD, "protocol")
    source = Archive(a.archive, 110)
    anchor = Archive(a.archive, 86)
    calibration = anchor.read(RANK + "/down-rank0.q8")
    captured = anchor.read(RANK + "/swiglu.f32")
    rank = json.loads(anchor.read(RANK + "/rank.json"))
    quant = Quantizer(a.libs)
    totals, sites, extremes = Counter(), {}, {}
    authority = hashlib.sha256()
    for pos in (189, 190, 191):
        for layer in range(14):
            site = f"{pos}/{layer}"

            xraw, raw, route = [
                source.read(f"{BOUNDARY}/{pos}.{name}-{layer}.bin")
                for name in ("attn_post_norm", "ffn_moe_swiglu_oai", "ffn_moe_topk")
            ]
            for data in (xraw, raw, route):
                authority.update(data)
            ids = struct.unpack("<4i", route)
            need(
                len(raw) == 4 * N * 4 and len(set(ids)) == 4 and min(ids) >= 0 and max(ids) < 128,
                "rank geometry",
            )
            x = weight_mask(quant.row(xraw, site + "/input"))
            per_site = Counter()
            for r, e in enumerate(ids):
                q = quant.row(raw[r * N * 4 : (r + 1) * N * 4], f"{site}/rank{r}")
                if (pos, layer, r) == (189, 0, 0):
                    need(
                        list(ids) == rank["logical"]
                        and e == 28
                        and raw == captured
                        and q == calibration,
                        "independent CPU0 activation, route or down Q8_0",
                    )
                row = price(x, weight_mask(q))
                per_site.update(row)
                for key in (
                    "causal_saved_half_bytes",
                    "oracle_saved_half_bytes",
                    "pack_saved_pages",
                ):
                    loc = dict(value=row[key], position=pos, layer=layer, rank=r, expert=e)
                    if key not in extremes or row[key] > extremes[key]["max"]["value"]:
                        extremes.setdefault(key, {})["max"] = loc
                    if "min" not in extremes[key] or row[key] < extremes[key]["min"]["value"]:
                        extremes[key]["min"] = loc
            totals.update(per_site)
            sites[site] = dict(per_site)
    need(
        totals["records"] == 168
        and quant.rows == 210
        and WINDOW == ((PAYLOAD + PAGE - 1) // PAGE) * PAGE,
        "incomplete population",
    )
    peak = extremes["oracle_saved_half_bytes"]["max"]["value"]
    return dict(
        schema="tesy.exact_operand_pages.v1",
        status="MEASURED_OPERANDS",
        method_sha256=METHOD,
        evaluator_sha256=sha(Path(__file__).read_bytes()),
        independent_quantizer_sha256=sha(Path(ARITH["__file__"]).read_bytes()),
        libs=LIBS,
        manifests=MANIFESTS,
        input_sha256=authority.hexdigest(),
        q8_sha256=quant.digest.hexdigest(),
        finite_matching_q8_rows=quant.rows,
        archive86_q8_sha256=sha(calibration),
        totals=dict(totals),
        by_site=sites,
        extrema=extremes,
        target_context=dict(
            required_read_reduction_ppm=REQUIRED_PPM, window_bytes=WINDOW, payload_bytes=PAYLOAD
        ),
        page_decision="NO_GO" if totals["pack_saved_pages"] == 0 else "FIXTURE_REQUIRED",
        oracle_volume_decision="NO_GO"
        if peak * 1_000_000 < REQUIRED_PPM * 2 * PAYLOAD
        else "FIXTURE_REQUIRED",
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "libs", "new-output-dir"):
        p.add_argument("--" + name, required=True, type=Path)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a)
    except FileNotFoundError as e:
        missing = Path(e.filename).resolve()
        result = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if missing.is_relative_to(a.archive.resolve())
            else "FAIL",
            "missing": missing.name,
        }
    except (ValueError, KeyError, OSError, TypeError, struct.error) as e:
        result = {"status": "FAIL", "reason": str(e)}
    tmp = a.new_output_dir / ".pending"
    tmp.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n")
    tmp.rename(a.new_output_dir / "receipt.json")
    print(
        result["status"],
        result.get("page_decision", ""),
        result.get("oracle_volume_decision", result.get("reason", "")),
    )
    raise SystemExit(result["status"] != "MEASURED_OPERANDS")
