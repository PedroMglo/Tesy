import copy
import struct
from pathlib import Path
from runpy import run_path

import pytest

B = run_path(str(Path(__file__).with_name("boundary.py")))
SHA = B["SHA"]


def views(ids, samples):
    rows = []
    p = 2044
    for call, widths in enumerate(((5,), (32, 32, 32, 32, 20), (1,)), 1):
        n = sum(widths)
        pos = list(range(p, p + n))
        tiles = []
        i = 0
        for t, k in enumerate(widths, 1):
            tiles.append((t, pos[i : i + k]))
            i += k
        has_output = call > 1
        rows.append(
            dict(
                request="fixture-T2",
                call=call,
                slot=0,
                seqs=[[0]] * n,
                rc=0,
                positions=pos,
                tokens=ids[p : p + n] if call < 3 else [samples[0]],
                mask=[0] * (n - 1) + [int(has_output)],
                tiles=tiles,
                offset=7,
                slot_i_batch=7 + n - 1 if has_output else -1,
                sampler_index=n - 1 if has_output else None,
                full_row0_alias=True,
                sampled_logits_count=0,
                n_outputs=int(has_output),
                vocab=201088,
            )
        )
        p += n
    return rows


def test_resolve_sampler_sites_and_faults():
    ids, sampled = list(range(2197)), list(range(47))
    rows = views(ids, sampled)
    cached = ids[:2044]

    def select():
        return B["select"](
            rows,
            cached,
            sampled,
            request="fixture-T2",
            prompt_sha=B["token_hash"](ids),
            samples_sha=B["token_hash"](list(range(47))),
        )

    sites = select()
    assert [(s["position"], s["tile_row"], s["sampler_row"], s["compact_row"]) for s in sites] == [
        (2196, 19, 147, 0),
        (2197, 0, 0, 0),
    ]
    for index, field, bad in (
        (1, "request", "T1"),
        (1, "slot", 1),
        (1, "seqs", [[1]] * 148),
        (2, "call", 2),
        (1, "tiles", [(1, list(range(2049, 2197)))]),
        (1, "slot_i_batch", 7 + 19),
        (1, "sampler_index", 0),
        (1, "sampled_logits_count", 32),
        (2, "full_row0_alias", False),
        (1, "mask", [1] * 148),
        (1, "tokens", [1] * 148),
        (2, "tokens", [123]),
        (0, "sampler_index", 0),
        (0, "rc", 1),
    ):
        old = rows[index][field]
        rows[index][field] = bad
        with pytest.raises(ValueError):
            select()
        rows[index][field] = old
    cached[100] += 1
    with pytest.raises(ValueError, match="prefix"):
        select()


def state(n, reverse=False):
    out = bytearray(struct.pack("<Ii", 0xAF143CD8, 0))
    for parity, positions in zip((1, 0), B["visible"](n - 1), strict=True):
        pos = list(range(*positions))
        if reverse:
            pos.reverse()
        out.extend(struct.pack("<II", 1, len(pos)))
        for p in pos:
            out.extend(struct.pack("<iIi", p, 1, 0))
        out.extend(struct.pack("<II", 0, 18))
        for k in range(2):
            for layer in range(parity, 36, 2):
                out.extend(struct.pack("<iQ", 1, 1024))
                for p in pos:
                    out.extend(struct.pack("<H", 1 + p + layer * 8 + k * 1024) * 512)
    return out


def test_live_cells_masks_equal_logits_and_distinct_components():
    blob = state(132)
    normal = B["decode_kv"](blob, 132)
    backwards = B["decode_kv"](state(132, True), 132)
    assert len(normal) == 72 and normal == backwards
    assert B["visible"](2196) == ((0, 2197), (2069, 2197))
    assert B["visible"](2197) == ((0, 2198), (2070, 2198))
    site = dict(position=2196)
    output = B["logit_digest"](bytes(201088 * 4))
    receipt = dict(site=site, logits=output, kv=normal)
    B["agree"](receipt, dict(site=site, logits=output, kv=backwards))
    blob[-1] ^= 1
    with pytest.raises(ValueError, match=r"swa.V.34"):
        B["agree"](receipt, dict(site=site, logits=output, kv=B["decode_kv"](blob, 132)))
    for index in (4, 8, 16, 24):
        broken = bytearray(blob)
        broken[index] ^= 1
        with pytest.raises(ValueError):
            B["decode_kv"](broken, 132)
    with pytest.raises(ValueError, match="extent"):
        B["decode_kv"](blob[:-1], 132)
    delta = copy.copy(receipt)
    delta["site"] = dict(position=2197)
    with pytest.raises(ValueError, match="sites"):
        B["agree"](receipt, delta)
    with pytest.raises(ValueError, match="non-finite"):
        B["logit_digest"](bytes(201087 * 4) + struct.pack("<f", float("nan")))


@pytest.mark.parametrize("kind,fmt", [("f16", "<e"), ("f32", "<f")])
def test_attention_mask_columns_and_slot_identity(kind, fmt):
    import math

    cells = [(0, i) for i in reversed(range(140))] + [(-1, -1), (1, 135)]
    for bank, lo in [("global", 0), ("swa", 8)]:
        data = bytearray().join(
            struct.pack(fmt, 0.0 if owner == 0 and lo <= pos <= 135 else -math.inf)
            for owner, pos in cells
        )
        check = B["verify_mask_row"]
        assert check(data, cells, bank=bank, query=135, kind=kind) == [lo, 136]
        with pytest.raises(ValueError, match="mask value"):
            check(data, list(reversed(cells)), bank=bank, query=135, kind=kind)
        where = struct.calcsize(fmt) * 4  # position 135 in physical column 4
        data[where : where + struct.calcsize(fmt)] = struct.pack(fmt, -0.0)
        with pytest.raises(ValueError, match="mask value"):
            check(data, cells, bank=bank, query=135, kind=kind)
