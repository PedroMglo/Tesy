"""Verify direct_io JSON independently. No filesystem device, weights or GPU needed here."""

import argparse
import copy
import errno
import hashlib
import json
import re
import unittest
from collections import Counter
from functools import cache
from pathlib import Path

COMPONENT = 4_406_400
PAYLOAD = 3 * COMPONENT
PAGE = 4096
SLOT = PAGE * ((PAYLOAD + PAGE - 1) // PAGE)
STRIDE = PAGE * ((SLOT + 3 * 11520 + PAGE - 1) // PAGE)
INDEX_SHA = "f8961dcdaa58aa7774e63150b76d69add0dd080181493838528c8f36de543a57"


def need(ok, label):
    if not ok:
        raise ValueError(label)


def geometry(index):
    """Check only the C290 index, never follow pack/model paths from metadata."""
    data = index.read_bytes()
    need(hashlib.sha256(data).hexdigest() == INDEX_SHA, "historical_index_sha256")
    obj = json.loads(data)
    need(
        (obj["alignment"], obj["memory_alignment"], obj["weight_window"], obj["stride"])
        == (PAGE, PAGE, SLOT, STRIDE),
        "geometry",
    )
    need(
        len(obj["experts"]) == 36 * 128 and obj["pack_bytes"] == STRIDE * 36 * 128,
        "pack_cardinality",
    )
    sizes = [COMPONENT] * 3 + [11520] * 3
    offsets = [0, COMPONENT, COMPONENT * 2, SLOT, SLOT + 11520, SLOT + 23040]
    for n, row in enumerate(obj["experts"]):
        need(
            (row["layer"], row["expert"], row["pack_offset"]) == (n // 128, n % 128, n * STRIDE),
            "physical_record_mapping",
        )
        cs = row["components"]
        need(
            len(cs) == 6
            and [c["size_bytes"] for c in cs] == sizes
            and [c["packed_relative_offset"] for c in cs] == offsets,
            "component_dimensions",
        )
        names = [
            f"blk.{n // 128}.ffn_{k}_exps.{t}"
            for t in ("weight", "bias")
            for k in ("gate", "down", "up")
        ]
        need([c["name"] for c in cs] == names, "view_order")
    return INDEX_SHA


@cache
def reference(expert):
    lengths = [COMPONENT] * 3 + [SLOT - PAYLOAD]
    window = hashlib.sha256()
    roles = []
    for k, n in enumerate(lengths):
        data = hashlib.shake_256(f"Tesy-C290-direct-v1/expert{expert}/area{k}".encode()).digest(n)
        window.update(data)
        roles.append(hashlib.sha256(data).hexdigest())
    return tuple(roles), window.hexdigest()


def gold(expert):
    return list(reference(expert)[0])


def live_gold():
    joined = "".join(reference(i)[1] for i in (1, 0, 1, 0))
    return hashlib.sha256(joined.encode("ascii")).hexdigest()


def verify_generation(g):
    need(
        (
            g["slot"],
            g["first_generation"],
            g["generation_before_syscall"],
            g["generation_after_syscall_before_return"],
            g["reassignment_generation"],
        )
        == (4, 1, 1, 1, 2)
        and g["state_after_return"] == "INVALID"
        and g["same_destination"] is True,
        "invalid_generation_or_ownership",
    )
    for key in ("owned_before_syscall", "owned_before_handback"):
        need(
            g[key]
            == dict(
                status="REJECT_OWNED",
                pread_calls=0,
                return_bytes=-1,
                errno=0,
                published=False,
                sha256=[],
            ),
            "inflight_claim_accepted",
        )
    need(
        g["guard_mutation_detected"] is True
        and g["live_neighbour_mutation_detected"] is True
        and g["live_sha256_at_checkpoints"] == [live_gold()] * 6,
        "live_neighbour_or_guard",
    )
    need(g["published_slots"] == [0, 3, 4, 5, 39], "terminal_publications")
    for name, expert in (("slot3_live", 0), ("slot5_live", 1), ("slot4_reassigned", 0)):
        need(
            g[name]
            == dict(
                status="PUBLISHED",
                pread_calls=1,
                return_bytes=SLOT,
                errno=0,
                published=True,
                sha256=gold(expert),
            ),
            "full_live_or_reassigned_bytes",
        )
    need(re.fullmatch(r"[0-9a-f]{8192}", g["tail_hex"]), "tail_extent")
    values = bytes.fromhex(g["tail_hex"])
    need(
        g["tail_histogram"] == {str(b): n for b, n in Counter(values).items()}
        and g["tail_sha256"] == hashlib.sha256(values).hexdigest(),
        "tail_observation",
    )


def verify(row, physical):
    expected = "PASS_BTRFS_NVME_DIRECT_FIXTURE" if physical else "PASS_SYNTHETIC_ONLY"
    need(row["status"] == expected, "scope")
    need(
        row["O_DIRECT"] is True
        and row["guard_pages_intact"] is True
        and row["private_pack_unlinked"] is True,
        "source_and_destinations",
    )
    need(
        (row["component"], row["payload"], row["slot_stride"], row["pack_stride"])
        == (COMPONENT, PAYLOAD, SLOT, STRIDE),
        "C290_geometry",
    )
    need(
        (row["logical_slots"], row["arena_VMA"], row["file_bytes"])
        == (40, 2 * PAGE + 40 * SLOT, 2 * STRIDE + SLOT - PAGE),
        "fixture_geometry",
    )
    if row["DIOALIGN_known"]:
        need(
            all(
                type(row[k]) is int and 0 < row[k] <= PAGE and PAGE % row[k] == 0
                for k in ("DIO_mem", "DIO_offset")
            ),
            "direct_io_alignment",
        )
    if physical:
        need(
            re.fullmatch(r"nvme\d+n\d+(?:p\d+)?", row["device"])
            and row["FIEMAP_count"] >= 1
            and row["mincore_checked"] is True
            and row["resident_before"] == 0
            and row["resident_after_positives"] == 0,
            "physical_filesystem_and_residency",
        )
    cases = row["cases"]
    need(
        set(cases)
        == {
            "slot0_expert1",
            "slot39_expert0",
            "wrong_offset",
            "short_eof",
            "failed_fd",
            "wrong_content_digest",
        },
        "cases",
    )
    for slot, expert in ((0, 1), (39, 0)):
        r = cases[f"slot{slot}_expert{expert}"]
        need(
            r["status"] == "PUBLISHED"
            and r["published"] is True
            and (r["pread_calls"], r["return_bytes"], r["errno"]) == (1, SLOT, 0),
            "publication",
        )
        need(r["sha256"] == gold(expert), "independent_gate_down_up_padding")
    for key, state, calls, size, error in [
        ("wrong_offset", "REJECT_OFFSET", 0, -1, 0),
        ("failed_fd", "REJECT_SYSCALL", 1, -1, errno.EBADF),
        ("short_eof", "REJECT_SHORT", 1, SLOT - PAGE, 0),
        ("wrong_content_digest", "REJECT_DIGEST", 1, SLOT, 0),
    ]:
        r = cases[key]
        need(
            r["status"] == state
            and r["published"] is False
            and (r["pread_calls"], r["return_bytes"], r["errno"]) == (calls, size, error),
            "negative_publication_or_syscall",
        )
    need(
        cases["wrong_content_digest"]["sha256"] == [cases["slot39_expert0"]["sha256"][0]],
        "misdirected_content",
    )
    verify_generation(row["failed_generation"])
    return {
        "status": expected,
        "verified_component_views": 15,
        "verified_padding_regions": 5,
        "terminal_publications": 5,
        "rejected_cases": 6,
        "live_slot_checkpoints": 6,
        "reassigned_slot_generation": 2,
        "failed_generation_tail_sha256": row["failed_generation"]["tail_sha256"],
        "failed_generation_tail_histogram": row["failed_generation"]["tail_histogram"],
        "source_index_sha256": INDEX_SHA,
    }


class Schema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def case(status, calls, size, err, hashes):
            return {
                "status": status,
                "pread_calls": calls,
                "return_bytes": size,
                "errno": err,
                "published": status == "PUBLISHED",
                "sha256": hashes,
            }

        a, b = gold(0), gold(1)
        cls.r = {
            "status": "PASS_BTRFS_NVME_DIRECT_FIXTURE",
            "O_DIRECT": True,
            "guard_pages_intact": True,
            "private_pack_unlinked": True,
            "component": COMPONENT,
            "payload": PAYLOAD,
            "slot_stride": SLOT,
            "pack_stride": STRIDE,
            "logical_slots": 40,
            "arena_VMA": 2 * PAGE + 40 * SLOT,
            "file_bytes": 2 * STRIDE + SLOT - PAGE,
            "DIOALIGN_known": True,
            "DIO_mem": PAGE,
            "DIO_offset": PAGE,
            "device": "nvme0n1p3",
            "FIEMAP_count": 2,
            "mincore_checked": True,
            "resident_before": 0,
            "resident_after_positives": 0,
            "failed_generation": {
                "slot": 4,
                "first_generation": 1,
                "generation_before_syscall": 1,
                "generation_after_syscall_before_return": 1,
                "reassignment_generation": 2,
                "state_after_return": "INVALID",
                "same_destination": True,
                "owned_before_syscall": case("REJECT_OWNED", 0, -1, 0, []),
                "owned_before_handback": case("REJECT_OWNED", 0, -1, 0, []),
                "guard_mutation_detected": True,
                "live_neighbour_mutation_detected": True,
                "live_sha256_at_checkpoints": [live_gold()] * 6,
                "published_slots": [0, 3, 4, 5, 39],
                "slot3_live": case("PUBLISHED", 1, SLOT, 0, a),
                "slot5_live": case("PUBLISHED", 1, SLOT, 0, b),
                "slot4_reassigned": case("PUBLISHED", 1, SLOT, 0, a),
                "tail_hex": "00" * PAGE,
                "tail_histogram": {"0": PAGE},
                "tail_sha256": hashlib.sha256(bytes(PAGE)).hexdigest(),
            },
            "cases": {
                "slot0_expert1": case("PUBLISHED", 1, SLOT, 0, b),
                "slot39_expert0": case("PUBLISHED", 1, SLOT, 0, a),
                "wrong_offset": case("REJECT_OFFSET", 0, -1, 0, []),
                "failed_fd": case("REJECT_SYSCALL", 1, -1, errno.EBADF, []),
                "short_eof": case("REJECT_SHORT", 1, SLOT - PAGE, 0, []),
                "wrong_content_digest": case("REJECT_DIGEST", 1, SLOT, 0, [a[0]]),
            },
        }

    def test_independent_geometry_and_gold(self):
        self.assertEqual(verify(self.r, True)["verified_component_views"], 15)

    def test_tail_is_observed_and_never_assumed_zero(self):
        row = copy.deepcopy(self.r)
        g = row["failed_generation"]
        data = bytes(range(256)) * 16
        g.update(
            tail_hex=data.hex(),
            tail_sha256=hashlib.sha256(data).hexdigest(),
            tail_histogram={str(i): 16 for i in range(256)},
        )
        self.assertEqual(verify(row, True)["terminal_publications"], 5)
        g["tail_histogram"] = {"0": PAGE}
        with self.assertRaisesRegex(ValueError, "tail_observation"):
            verify(row, True)

    def test_reject_misreported_ownership_or_corrupt_live_data(self):
        for field, value in (
            ("generation_before_syscall", 2),
            ("generation_after_syscall_before_return", 2),
            ("reassignment_generation", 1),
            ("same_destination", False),
            ("live_sha256_at_checkpoints", [live_gold()] * 5 + ["0" * 64]),
            ("guard_mutation_detected", False),
            ("live_neighbour_mutation_detected", False),
            ("owned_before_handback", self.r["cases"]["slot0_expert1"]),
            ("slot4_reassigned", self.r["cases"]["slot0_expert1"]),
        ):
            row = copy.deepcopy(self.r)
            row["failed_generation"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify(row, True)

    def test_reject_swapped_slot_or_role(self):
        bad = copy.deepcopy(self.r)
        z = bad["cases"]["slot0_expert1"]["sha256"]
        z[0], z[2] = z[2], z[0]
        with self.assertRaisesRegex(ValueError, "gate_down_up"):
            verify(bad, True)

    def test_short_read_published_and_io_fallback_rejected(self):
        bad = copy.deepcopy(self.r)
        bad["cases"]["short_eof"]["published"] = True
        with self.assertRaisesRegex(ValueError, "negative_publication"):
            verify(bad, True)
        for case in (
            {"resident_after_positives": 1},
            {"mincore_checked": False},
            {"device": "sda1"},
            {"FIEMAP_count": 0},
        ):
            with self.subTest(case=case), self.assertRaisesRegex(ValueError, "physical_filesystem"):
                verify(self.r | case, True)

    def test_mismatched_stride_mode_and_data_budget(self):
        for update in (
            {"pack_stride": SLOT},
            {"status": "PASS_SYNTHETIC_ONLY"},
            {"file_bytes": 2**30},
        ):
            with self.subTest(update=update), self.assertRaises(ValueError):
                verify(self.r | update, True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--mode", choices=("fixture", "nvme"), required=True)
    parser.add_argument("--index", type=Path, required=True)
    args = parser.parse_args()
    geometry(args.index)
    print(
        json.dumps(
            verify(json.loads(args.receipt.read_bytes()), args.mode == "nvme"), sort_keys=True
        )
    )
