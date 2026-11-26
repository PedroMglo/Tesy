import unittest

import screen


class TestService(unittest.TestCase):
    def fixture(self, layer):
        key = (layer, 45, 3, 4)
        rows = []
        for stamp, (kind, component) in enumerate(
            [(5, -1), *[(k, c) for c in range(3) for k in (6, 7, 8, 9)], (10, -1)]
        ):
            rows.append(
                dict(
                    layer=layer,
                    expert=45,
                    slot=3,
                    gen=4,
                    kind=kind,
                    component=component,
                    call=1,
                    us=stamp,
                )
            )
        jobs = {key: dict(begin=0, end=13, read=3, copy=10, owner=1)}
        return key, rows, jobs

    def test_component_and_residual_separated(self):
        for layer in (0, 25):
            key, rows, jobs = self.fixture(layer)
            split, summary = screen.measured_components(rows, jobs)
            self.assertEqual(split[key], (3, 3, 7))
            for treatment, expected in [
                ("control", 10),
                ("free_cpu_set", 7),
                ("free_cpu_set_and_residual", 0),
            ]:
                out = screen.adjust((jobs,), split, treatment)[0][key]
                self.assertEqual(
                    (out["read"], out["copy"]), (3, expected if layer < 25 else 10)
                )
            self.assertEqual(summary["CPU" if layer == 0 else "CUDA0"]["jobs"], 1)
            self.assertEqual(jobs[key]["copy"], 10)

    def test_cannot_count_overlapping_or_unidentified_set(self):
        for mutation in ("owner", "component", "time", "duplicate", "missing"):
            key, rows, jobs = self.fixture(0)
            if mutation == "owner":
                rows[4]["call"] = 2
            if mutation == "component":
                rows[4]["component"] = 2
            if mutation == "time":
                rows[4]["us"] = 17
            if mutation == "duplicate":
                rows.append(rows[4])
            if mutation == "missing":
                del rows[4]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                screen.measured_components(rows, jobs)


if __name__ == "__main__":
    unittest.main()
