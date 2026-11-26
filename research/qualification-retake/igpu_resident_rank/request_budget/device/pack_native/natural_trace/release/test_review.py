"""Small release and accounting counterexamples, independent of qualified private data."""

import unittest
from pathlib import Path
from runpy import run_path

R = run_path(Path(__file__).with_name("review.py"))
Row = R["SERVICE"]["PRIOR"]["pfj"]["Row"]
SLAB, W = R["SLAB"], R["WINDOW"]
PC = {"first_final_s": 14, "decode_s": 8}


def row(kind, ns, e=0, call_no=1, wave=0, **kw):
    defaults = dict.fromkeys(Row._fields, 0)
    defaults.update(
        kind=kind,
        ns=ns,
        call=call_no,
        tile=1,
        layer=0,
        slot=e,
        gen=1,
        expert=e,
        wave=wave,
        component=-1,
        fd=5,
    )
    return Row(**(defaults | kw))


def job(e, t, w=0, reason=0):
    return [
        row(11, t, e, wave=w),
        row(12, t + 1, e, wave=w, a=reason),
        row(13, t + 2, e, wave=w, worker=e % 4),
        row(30, t + 13, e, wave=w, begin=t + 3, b=W, c=W, worker=e % 4),
        *[
            row(
                16,
                t + 15 + 2 * i,
                e,
                wave=w,
                begin=t + 13 + 2 * i,
                a=SLAB,
                component=i,
                worker=e % 4,
            )
            for i in range(3)
        ],
        row(17, t + 20, e, wave=w, worker=e % 4),
    ]


def trace():
    data = [row(5, 2, e=4, a=2), row(9, 10)]
    # Six disk jobs in w0. Five are demanded; the sixth is a preload for w1.
    for e, t in enumerate((12, 12, 12, 12, 34, 34)):
        data.extend(job(e + 6, t, reason=int(e == 5) * 2))
    data.extend(row(10, 58, e=i) for i in range(6, 11))
    data.extend([row(10, 58, e=4), row(23, 60), row(9, 71, wave=1), row(10, 73, e=11, wave=1)])
    data.extend(job(12, 74, 1))
    data.extend(
        [
            row(10, 95, e=12, wave=1),
            row(23, 98, wave=1),
            row(9, 130, call_no=2),
            row(23, 140, call_no=2),
        ]
    )
    host = {
        "calls": [
            {"enter_ns": 2, "enter_begin_ns": 1, "return_ns": 100},
            {"enter_ns": 120, "return_ns": 150},
        ],
        "callback_spans": [(1, 10, 60), (1, 71, 98), (2, 130, 140)],
    }
    return sorted(data, key=lambda e: e.ns), host


class Release(unittest.TestCase):
    def test_volume_and_overlap(self):
        rows, host = trace()
        result = R["classify"](rows, host, PC)
        strict = result["per_wave_fixed_release"]["first_wave"]["total"]
        seen = result["per_wave_fixed_release"]["as_observed"]["total"]
        self.assertEqual(
            (strict["jobs"], strict["read_floor_ns"], strict["read_set_floor_ns"]), (5, 12, 20)
        )
        self.assertEqual((seen["jobs"], seen["read_floor_ns"]), (6, 22))
        self.assertEqual(result["unique_first_use"]["preload_or_other_release"], 1)
        self.assertEqual(result["earliest_allowed_at_entry"]["volumes"]["jobs"], 7)
        self.assertEqual(result["prefill_callback_union_ns"], 87)
        self.assertEqual(result["combined_call_envelope_ns"], 149)
        self.assertEqual(result["unique_first_use"]["initial_ready_or_loading"], 1)
        self.assertEqual(
            result["earliest_allowed_at_entry"]["volumes"]["payload_bytes"], 7 * 3 * SLAB
        )

    def test_reject_missing_set_wrong_worker_and_early_service(self):
        for field, value in (("worker", 3), ("a", 0), ("begin", 1), ("component", 2)):
            rows, host = trace()
            i = next(i for i, r in enumerate(rows) if r.kind == 16)
            rows[i] = rows[i]._replace(**{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                R["classify"](rows, host, PC)
        rows, host = trace()
        rows = [r for r in rows if not (r.kind == 16 and r.expert == 6 and r.component == 2)]
        with self.assertRaisesRegex(ValueError, "three SETs"):
            R["classify"](rows, host, PC)

    def test_prior_preload_promotion_and_other_generation(self):
        rows, host = trace()
        # e11 waits in the queue across the boundary, then receives promotion.
        rows = [
            v._replace(ns=v.ns + 39, begin=v.begin + 39 if v.begin else 0)
            if v.expert == 11 and v.kind in (13, 30, 16, 17)
            else v
            for v in rows
        ]
        rows.append(row(12, 74, e=11, wave=1, a=1))
        # e12 was prefetched before the generation that serves its first demand.
        rows = [v._replace(gen=2) if v.expert == 12 else v for v in rows]
        rows.extend(job(12, 34, reason=2))
        result = R["classify"](sorted(rows, key=lambda v: v.ns), host, PC)
        counts = result["unique_first_use"]
        self.assertEqual(counts["earlier_other_generation"], 1)
        self.assertEqual(counts["preload_or_other_release"], 1)
        self.assertEqual(result["earliest_allowed_at_entry"]["volumes"]["jobs"], 7)
        self.assertEqual(result["per_wave_fixed_release"]["as_observed"]["total"]["jobs"], 5)

    def test_no_double_time_and_rate_boundary(self):
        rows, host = trace()
        host["callback_spans"][1] = (1, 15, 98)
        with self.assertRaisesRegex(ValueError, "different host spans"):
            R["classify"](rows, host, PC)
        self.assertEqual(R["four_lanes"]([]), 0)
        self.assertEqual(R["four_lanes"]([2, 7, 9]), 9)
        self.assertEqual(
            R["projections"]({"first_final_s": "10", "decode_s": "1"}, 0, 0)["6"]["decision"],
            "HEADROOM_ONLY",
        )
        self.assertEqual(
            R["projections"]({"first_final_s": "10", "decode_s": "1"}, 0, 1)["6"]["decision"],
            "NO_GO_FIXED_SCENARIO",
        )

    def test_initial_loading_and_sufficient_padding_short(self):
        rows, host = trace()
        i = next(i for i, v in enumerate(rows) if v.kind == 5)
        rows[i] = rows[i]._replace(a=1)
        i = next(i for i, v in enumerate(rows) if v.kind == 30)
        rows[i] = rows[i]._replace(c=3 * SLAB)
        result = R["classify"](rows, host, PC)
        self.assertEqual(result["unique_first_use"]["initial_ready_or_loading"], 1)
        vol = result["earliest_allowed_at_entry"]["volumes"]
        self.assertEqual(vol["requested_bytes"] - vol["returned_bytes"], W - 3 * SLAB)


if __name__ == "__main__":
    unittest.main()
