import unittest

from screen import cold, mark_groups, optimizer, verify_witness


def fixture():
    keys = [(0, 11, 1, 1), (0, 22, 2, 1), (0, 11, 3, 2), (0, 33, 4, 1)]
    jobs = {
        w: dict(read=read, copy=copy, owner=1, order=i, begin=0, end=30)
        for i, (w, read, copy) in enumerate(zip(keys, (12, 11, 19, 6), (2, 3, 5, 4), strict=True))
    }
    template = dict(call=1, layer=0, pre=4, attention=3, after=1, wait=0)
    groups = [dict(template, need=keys[:2]), dict(template, need=keys[2:])]
    return (jobs, groups, 6, 80, [], [], 0), {keys[2]}


def reference(data, free):
    _, stats, _ = cold.maxima(data, free)
    jobs = {w: {**j, "read": 0.0 if w in free else j["read"]} for w, j in data[0].items()}
    rows = []
    for scale in (0.8, 1.0, 1.2):
        rows.append(
            dict(
                scale=scale,
                baseline_us=cold.c295.simulate(data, None, scale, cold.ARENA)["decode_us"],
                ideal_us=cold.c295.simulate((jobs, *data[1:]), None, scale, cold.ARENA)[
                    "decode_us"
                ],
            )
        )
    return {"scales": rows, "service_at_scale_1": stats}


class Warm(unittest.TestCase):
    def test_first_service_classification_and_replay_all_scales(self):
        data, hits = fixture()
        sealed = reference(data, hits)
        allowed = {(0, 11), (0, 22)}
        groups, first = mark_groups(data, hits, allowed)
        self.assertEqual(
            [[r[-1] for r in g] for g in groups], [["eligible", "eligible"], ["free", "cold"]]
        )
        self.assertEqual(len(first), 3)
        solutions = optimizer.resolve(groups, (0, 1, 2))
        for k in (0, 1, 2):
            out = verify_witness(data, hits, first, allowed, k, solutions[k], sealed)
            self.assertEqual(out["charged_ingress_bytes"], out["identities_chosen"] * 13_219_200)
            for scale in out["scales"]:
                self.assertAlmostEqual(
                    scale["warm_gain_over_cold_us"], scale["scale"] * solutions[k]["gain_us"]
                )
        self.assertEqual(solutions[1]["gain_us"], 0)
        self.assertEqual(solutions[2]["gain_us"], 11)

    def test_reject_ineligible_or_forged_solution(self):
        data, hits = fixture()
        allowed = {(0, 22)}
        groups, first = mark_groups(data, hits, allowed)
        solution = optimizer.resolve(groups, (1,))[1]
        for change in (
            {"chosen": [(0, 33)]},
            {"chosen": [(0, 22), (0, 22)]},
            {"gain_us": 19},
            {"group_max_sum_us": -1},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_witness(
                    data, hits, first, allowed, 1, {**solution, **change}, reference(data, hits)
                )
        with self.assertRaises(ValueError):
            mark_groups(data, set(), None)

    def test_any_vs_earlier_route_or_physical_pool(self):
        data, hits = fixture()
        pools = (None, {(0, 11), (0, 22)}, {(0, 11), (0, 33)})
        answers = [
            optimizer.resolve(mark_groups(data, hits, a)[0], (2,))[2]["gain_us"] for a in pools
        ]
        self.assertGreaterEqual(answers[0], max(answers[1:]))
        self.assertNotEqual(answers[1], answers[2])


if __name__ == "__main__":
    unittest.main()
