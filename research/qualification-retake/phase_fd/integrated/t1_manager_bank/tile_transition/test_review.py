import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review  # noqa: E402


def sample(arm):
    ref = arm == "reference"
    gold = {"records": [{"role_sha256": [f"role-{r}-{k}" for k in range(3)]} for r in range(6)]}

    def hashes(e):
        return gold["records"][review.RECORDS.get(e, 0)]["role_sha256"]

    B = [4, 2, 0, 1] if ref else [2, 4, 6, 7]
    ps = [[0, 1, 2, 3], [6, 4, 0, 1], [3, 5, *B[:2]], [*B[2:], 3, 5]]
    ws = []
    for idx, pool in enumerate(ps):
        w = idx % 2
        m0 = [1, 1, 1, 1, 1, 1, 0, 0]
        ws.append(
            dict(
                pool=pool,
                demand_slots=pool[: 2 if w else 4],
                mask=([1 - x for x in m0] if w else m0),
                ids=pool + (pool[2:] + pool[:2] if w else pool),
                keep=[int(s in pool or (not w and s in ps[idx + 1][:2])) for s in range(40)],
            )
        )
    operations = (
        [("warm", e, e, "disk") for e in range(40)]
        + [("A", 40, 4, "disk")]
        + [("B", e, s, "disk") for e, s in enumerate(B, 41)]
    )
    if not ref:
        operations += [
            ("restore", e, s, source)
            for s, e, source in [
                (0, 43, "scratch"),
                (1, 44, "scratch"),
                (2, 42, "scratch"),
                (4, 41, "scratch"),
                (6, 6, "disk" if arm == "disk" else "bank"),
                (7, 7, "disk"),
            ]
        ]
    state = [{"slot": s, "generation": 0, "expert": -1} for s in range(40)]
    jobs = []
    for phase, e, s, src in operations:
        x = state[s]
        x.update(generation=x["generation"] + 1, expert=e)
        jobs.append(
            dict(
                phase=phase,
                expert=e,
                slot=s,
                generation=x["generation"],
                source=src,
                sets=3,
                reads=int(src == "disk"),
                publications=1,
            )
        )
        if phase == "B" and e == 44:
            before = copy.deepcopy(state)
    row = dict(
        arm=arm,
        status="PASS_C291_TILE_TRANSITION_CPU",
        workers=4,
        destructor_returned=True,
        preloads=3,
        waves=ws,
        old_reader={
            "6": hashes(43 if arm == "broken" else 6),
            "4": hashes(42 if arm == "broken" else 40),
        },
        capture=None if ref else dict(slot=6, expert=6, generation=1, role_sha256=hashes(6)),
        scratch_bytes=0 if ref else 4 * review.W,
        capture_bytes=0 if ref else review.W,
        jobs=jobs,
        before_restore=before,
        held_jobs=[dict(before[s], claimed=True, state=1) for s in B],
        held_distinct_workers=4,
        decode_ids=[6, 7, 2, 4],
        terminal=[dict(x, role_sha256=hashes(x["expert"])) for x in state],
    )
    return copy.deepcopy(row), gold


class Oracle(unittest.TestCase):
    def test_family(self):
        rows = {a: sample(a)[0] for a in review.ARMS}
        stats = review.family(rows, sample("reference")[1])
        self.assertEqual([stats[a]["disk_reads"] for a in review.ARMS], [45, 47, 46, 46])

    def test_negative(self):
        for path, wrong in [
            (("waves", 3, "ids", 2), 19),
            (("waves", 1, "mask", 0), 1),
            (("old_reader", "6", 2), "wrong"),
            (("jobs", 0, "sets"), 2),
            (("terminal", 6, "generation"), 1),
            (("held_jobs", 0, "claimed"), False),
        ]:
            with self.subTest(path=path):
                row, gold = sample("bank")
                ref = row
                for i in path[:-1]:
                    ref = ref[i]
                ref[path[-1]] = wrong
                with self.assertRaises(ValueError):
                    review.case("bank", row, gold)


if __name__ == "__main__":
    unittest.main()
