import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

F = Path(__file__).with_name("screen.py")
spec = importlib.util.spec_from_file_location("host_cache", F)
l2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(l2)


def ev(kind, layer, slot, gen, expert, call=1, a=0, c=0):
    return SimpleNamespace(
        kind=kind, layer=layer, slot=slot, gen=gen, expert=expert, call=call, a=a, c=c
    )


def key(e):
    return e.layer, e.slot, e.gen, e.expert


class HostCache(unittest.TestCase):
    def test_exact_memory(self):
        self.assertEqual(
            (l2.additional(0), l2.additional(239), l2.additional(353)), (0, 3212959744, 4720263168)
        )
        self.assertGreater(l2.additional(240), 3 * 2**30)
        self.assertGreater(l2.additional(354), l2.STOP - 16191946752 - l2.JOURNAL)

    def test_pinned_hit_cannot_be_evicted_by_concurrent_publication(self):
        c = l2.Cache(1)
        a = (2, 0, 1, 8)
        b = (1, 0, 1, 2)
        again = (2, 0, 2, 8)
        c.lookup(a, (2, 8), "prefill_cpu")
        c.publish(a)
        c.lookup(again, (2, 8), "decode_cpu")
        c.lookup(b, (1, 2), "decode_cpu")
        c.publish(b)
        c.publish(again)
        sums = c.finish(
            {again},
            {a: (1, l2.TRIPLE), again: (3, l2.TRIPLE + 1024), b: (3, l2.TRIPLE)},
            {a: l2.TRIPLE},
        )
        self.assertEqual(sums["required_prefill_miss_generations"], 1)
        self.assertEqual(sums["decode_hits"], 1)
        self.assertEqual(sums["prices"]["decode_cpu"]["bypassed"], 1)
        self.assertEqual(sums["prices"]["decode_cpu"]["returned_bytes_avoided"], l2.TRIPLE + 1024)

    def test_both_denominators_and_rounding(self):
        row = dict(predicted_n=47, prefill_s=10.0000000001, decode_s=8, first_final_s=10.0000000009)
        self.assertEqual(l2.budget(row, 47), (10166666668, 45750000006))
        self.assertEqual(l2.budget(row, 46), (10333333335, 46500000008))

    def test_returns_after_cut_are_only_charged_by_origin(self):
        g = (0, 0, 1, 4, 2)
        decode = (0, 1, 1, 5, 3)
        rows = [ev(13, *g), ev(15, *g, c=l2.SLAB), ev(2, *g), ev(15, *g, c=2 * l2.SLAB)]
        rows += [ev(17, *g), ev(13, *decode), ev(15, *decode, c=l2.TRIPLE), ev(17, *decode)]
        result = l2.replay(rows, key)["capacities"][0]
        self.assertEqual(result["remaining_origin_bytes_by_prefill_return"], l2.SLAB)
        self.assertEqual(result["prices"]["prefill_cpu"]["baseline_returned_bytes"], l2.TRIPLE)

    def test_inherited_exempt_and_reload_of_entry_resident(self):
        events = [ev(5, 0, 0, 2, 8, a=2), ev(5, 0, 1, 3, 9, a=1)]
        args = [(0, 0, 4, 8, 2), (0, 1, 5, 9, 2), (0, 2, 1, 17, 3)]
        for layer, slot, gen, expert, call in args:
            tpl = (layer, slot, gen, expert, call)
            events.extend((ev(13, *tpl), ev(15, *tpl, c=l2.TRIPLE), ev(17, *tpl), ev(10, *tpl)))
        out = l2.replay(events, key)
        self.assertEqual(out["required_distinct"], 1)
        self.assertEqual(out["cold_fixed_primary_floor_bytes"], l2.TRIPLE)
        self.assertEqual(out["initial_resident_reloads"], 1)
        self.assertEqual(out["capacities"][1]["required_prefill_payload_bytes"], 2 * l2.TRIPLE)
