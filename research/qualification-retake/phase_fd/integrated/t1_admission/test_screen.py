import importlib.util
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location("t1_admission", Path(__file__).with_name("screen.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def event(kind, **kw):
    return m.t2.fd.Row(*([0] * len(m.t2.fd.Row._fields)))._replace(kind=kind, **kw)


def ranks(ids):
    return event(27, a=sum(e << (8 * i) for i, e in enumerate(ids)))


class CausalAdmission(unittest.TestCase):
    def test_votes_cannot_acquire_or_recover_an_earlier_offer(self):
        initial = event(5, expert=1, gen=1, a=2)

        def replace(old, new, gen):
            return [event(11, a=old, expert=new, gen=gen), event(17, expert=new, gen=gen)]

        prefix = [initial, *replace(1, 2, 2)]
        prior = ranks([2, 100, 101, 102])
        late = m.select([*prefix, *replace(2, 3, 3), prior], 1)["banks"]
        early = m.select([*prefix, prior, *replace(2, 3, 3)], 1)["banks"]
        self.assertEqual(late["votes"]["ordered_keys"], [[0, 1]])
        self.assertEqual(early["votes"]["ordered_keys"], [[0, 2]])
        self.assertEqual(late["recency"], early["recency"])
        self.assertEqual(late["votes"]["tier"]["cpu"]["refused"], 1)
        self.assertNotIn([0, 100], early["votes"]["ordered_keys"])

    def test_capacity_full_strict_tie_refresh_order_and_tiers(self):
        bank = m.Admission(2, True)
        scores = Counter()
        x, y, z, t = (27, 1), (0, 3), (1, 4), (3, 5)
        for n, k in enumerate((x, y, x, z)):
            bank.offer(k, scores, n)
        self.assertEqual(set(bank.bank), {x, y})
        scores[z] = 1
        bank.offer(z, scores, 4)
        self.assertEqual(set(bank.bank), {x, z})
        scores[x] = 3
        scores[t] = 2
        bank.offer(t, scores, 5)
        result = bank.result()
        self.assertEqual(result["ordered_keys"], [list(x), list(t)])
        self.assertEqual(result["tier"]["cpu"]["discarded_in_t1"], 2)
        self.assertEqual(result["tier"]["cuda"]["installs"], 1)
        self.assertEqual(result["tier"]["cuda"]["refreshes"], 1)
        self.assertEqual(result["tier"]["cpu"]["install_bytes"], 3 * m.B)

    def test_invalid_ranks_and_only_live_generations(self):
        for seq in (
            [ranks([1, 2, 3, 3])],
            [ranks([200, 2, 3, 4])],
            [event(5, a=1, expert=3, gen=1), event(11, a=3, gen=2, expert=5)],
            [event(5, a=2, expert=3, gen=1), event(11, a=3, gen=4, expert=5)],
        ):
            with self.subTest(seq=seq), self.assertRaises(ValueError):
                m.select(seq, 1)
        result = m.select(
            [
                event(5, a=0, expert=-1),
                event(11, a=-1, expert=2, gen=1),
                event(17, expert=2, gen=1),
            ],
            1,
        )
        self.assertEqual(result["banks"]["votes"]["ordered_keys"], [])

    def test_failed_capture_never_opens_journal(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            digest = m.save(directory / "receipt.json", dict(status="FAIL_PRESERVED"))
            args = SimpleNamespace(capture_dir=directory, capture_sha256=digest)
            with self.assertRaisesRegex(ValueError, "validated natural family"):
                m.get_prefix(args)
            self.assertFalse((directory / "raw").exists())


if __name__ == "__main__":
    unittest.main()
