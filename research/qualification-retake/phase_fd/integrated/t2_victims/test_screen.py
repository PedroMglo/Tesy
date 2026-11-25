import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location(
    "victim_screen", Path(__file__).with_name("screen.py")
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def gen(i, expert):
    return (0, i % 2, i, expert)


def record(kind, expert, g, *, old=0, call=1):
    return SimpleNamespace(
        kind=kind, expert=expert, layer=0, slot=0, gen=g, a=old, call=call, tile=1, wave=0, c=m.T
    )


class VictimPolicy(unittest.TestCase):
    def test_hit_does_not_refresh_rank_and_pin_defers_reuse(self):
        c = m.Victims(2)
        s = "prefill_cpu"
        for i in range(2):
            g = gen(1 + i, 10 + i)
            c.reserve(g, (0, i), s)
            c.dispatch(g)
            c.publish(g)
        g = gen(5, 0)
        c.reserve(g, None, s)
        self.assertEqual(list(c.resident), [(0, 0), (0, 1)])
        q = gen(6, 20)
        c.reserve(q, (0, 2), s)
        self.assertEqual(list(c.resident), [(0, 0), (0, 2)])
        for cur in (g, q):
            c.dispatch(cur)
            c.publish(cur)
        r = c.report()["by_phase_tier"][s]
        self.assertEqual((r["hits"], r["unused_installs"], r["reused_installs"]), (1, 2, 1))

    def test_only_pinned_entry_makes_victim_bypass(self):
        c = m.Victims(1)
        s = "decode_cuda"
        g = (35, 0, 1, 9)
        c.reserve(g, (35, 0), s)
        c.dispatch(g)
        c.publish(g)
        q = (35, 1, 2, 0)
        c.reserve(q, (35, 9), s)
        c.dispatch(q)
        c.publish(q)
        stats = c.report()["by_phase_tier"][s]
        self.assertEqual(stats["pinned_bypasses"], 1)
        self.assertEqual(stats["victim_to_ram_bytes"], m.T)
        self.assertEqual(stats["ram_to_staging_bytes"], m.T)

    def test_reloaded_initial_key_hits_only_in_victim_arm(self):
        rows = [record(5, 3, 1, old=2)]
        for i, (key, old) in enumerate(((7, 3), (3, 7)), 2):
            rows.extend(record(kind, key, i, old=old) for kind in (11, 10, 13, 15, 17))
        mandatory = {(0, 0, 2, 7): (1, 1, 0, 0)}
        distinct, arms = m.replay(rows, mandatory, (0, 3))
        self.assertEqual(distinct, 1)
        self.assertEqual([a["mandatory_hits"] for a in arms], [0, 0])
        self.assertEqual([a["prefill_origin_bytes_by_return"] for a in arms], [2 * m.T, m.T])
        with self.assertRaisesRegex(ValueError, "already available"):
            m.replay(rows, {(0, 0, 3, 3): (1, 1, 0, 0)}, (3,))


if __name__ == "__main__":
    unittest.main()
