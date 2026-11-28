import itertools
import struct
from pathlib import Path
from runpy import run_path

OPS = run_path(Path(__file__).resolve().parents[1] / "research/ready-experts/operands/check.py")


def test_exact_weight_byte_pairs_use_low_and_high_half_of_the_block():
    a = [1] * 32
    for n in (0, 1, 16):
        a[n] = 0
    row = OPS["weight_mask"](struct.pack("<e32b", 1, *a))
    assert (row.inactive, row.empty_blocks, row.saved_nibbles) == (3, 0, 3)
    assert row.needed_bytes == bytes([1, 0] + [1] * 15)
    zero_scale = OPS["weight_mask"](struct.pack("<e32b", 0, *a))
    assert zero_scale.needed_bytes == bytes(17) and zero_scale.saved_nibbles == 34


def test_aligned_pages_agree_with_full_storage_including_crossings_and_padding():
    masks = list(map(bytes, itertools.product((0, 1), repeat=3)))
    for roles in itertools.product(masks, repeat=2):
        explicit = b"".join(role * 3 for role in roles)
        for width in (1, 2, 4, 7, 8, 15, 24):
            direct = sum(1 not in explicit[i : i + width] for i in range(0, len(explicit), width))
            assert OPS["saved_pages"](roles, 3, width) == direct


def test_down_oracle_cannot_charge_the_same_weights_twice():
    active = OPS["weight_mask"](struct.pack("<e32b", 1, *([1] * 32)) * 90)
    zero = OPS["weight_mask"](bytes(34 * 90))
    d = OPS["price"](active, zero)
    assert d["causal_saved_half_bytes"] == 2 * OPS["PAYLOAD"] // 3
    assert d["oracle_saved_half_bytes"] == 2 * OPS["PAYLOAD"]
    d = OPS["price"](zero, zero)
    assert d["causal_saved_half_bytes"] == d["oracle_saved_half_bytes"] == 2 * OPS["PAYLOAD"]
    assert d["pack_saved_pages"] * 4096 == OPS["WINDOW"]
