import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from runpy import run_path

S = run_path(str(Path(__file__).resolve().with_name("score.py")))
Wave = S["Wave"]
HIT, MISS = (0, 0, 1, 7), (0, 1, 1, 8)
BANK = {(0, 7)}


def wave(call, start, begin_drain, end_drain, reserves, required):
    return Wave(
        (call, 1, 0, 0),
        start,
        begin_drain,
        start + 100,
        end_drain,
        set(reserves),
        set(required),
        required,
    )


class TestBound(unittest.TestCase):
    def test_pending_and_drained(self):
        waves = [
            wave(1, 0, True, False, [HIT], {}),
            wave(3, 100, False, True, [MISS], {MISS: 40}),
            wave(47, 200, True, True, [], {}),
        ]
        phases, n, extra = S["bound"](waves, BANK, True, 225)
        self.assertEqual((n, extra), (1, 0))
        self.assertEqual(phases["decode_first"]["propagated_ns"], 100)
        self.assertEqual(phases["decode_first"]["floor_1x_ns"], 40)
        self.assertEqual(phases["prefill"]["floor_1x_ns"], 0)
        persistent, _, extra = S["bound"](waves, BANK, False, 225)
        self.assertEqual(extra, 25)
        self.assertEqual(persistent["decode_tail"]["propagated_ns"], 100)
        no_hits, used, extra = S["bound"](waves, set(), False, 225)
        self.assertEqual((used, extra), (0, 0))
        self.assertEqual(sum(g["callback_ns"] for g in no_hits.values()), 0)

    def test_parallel_floor_and_preload(self):
        others = [(0, n, 1, n) for n in range(9, 15)]
        required = dict.fromkeys(others[:5], 40)
        target = wave(1, 0, True, True, [HIT, *others], required)
        phases, _, _ = S["bound"]([target], BANK, True, 100)
        self.assertEqual(phases["prefill"]["floor_1x_ns"], 50)
        self.assertEqual(phases["prefill"]["required_jobs_CPU"], 5)
        target.required_service[others[0]] = 101
        with self.assertRaises(ValueError):
            S["bound"]([target], BANK, False, 100)

    def test_client_cut_and_common(self):
        phases = {
            n: Counter(callback_ns=c)
            for n, c in (("prefill", 20), ("decode_first", 30), ("decode_tail", 40))
        }
        r = S["adjudicate"](phases, 10**10 + 51, S["ALLOW"] + 70, 1, 5)["free"]
        self.assertEqual(
            (r["credit_first_ns"], r["credit_decode_ns"], r["shared_credit_ns"]), (50, 70, 30)
        )
        self.assertEqual(r["joint"], "NO_GO_FIXED_SCENARIO")
        self.assertEqual(r["first_margin_if_client_tail_free_ns"], 0)
        self.assertEqual(r["first_margin_with_tail_and_all_pre_stream_free_ns"], 5)

    def test_archive_digest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "session"
            (root / "ON").mkdir(parents=True)
            p = root / "ON/a"
            p.write_bytes(b"x")
            auth = {"files": {"session/ON/a": {"bytes": 1, "sha256": S["digest"](p)}}}
            S["authenticate_raw"](root, auth, ["a"])
            p.write_bytes(b"y")
            with self.assertRaises(ValueError):
                S["authenticate_raw"](root, auth, ["a"])
            with self.assertRaises(ValueError):
                S["pinned"](p, "0" * 64)
            p.write_text(json.dumps({"a": 42}))
            self.assertEqual(S["pinned"](p, S["digest"](p)), {"a": 42})


if __name__ == "__main__":
    unittest.main()
