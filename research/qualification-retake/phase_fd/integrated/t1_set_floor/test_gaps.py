import importlib.util
import unittest
from pathlib import Path

sp = importlib.util.spec_from_file_location(
    "serial_worker_gap_test", Path(__file__).with_name("gaps.py")
)
m = importlib.util.module_from_spec(sp)
sp.loader.exec_module(m)


def event(kind, ns, begin=0, component=-1):
    values = {key: 0 for key in m.src.fd.Row._fields}
    return m.src.fd.Row(
        **(
            values
            | dict(
                kind=kind,
                call=2,
                tile=3,
                layer=7,
                wave=5,
                worker=1,
                slot=4,
                expert=21,
                gen=11,
                ns=ns,
                begin=begin,
                component=component,
            )
        )
    )


class WorkerGap(unittest.TestCase):
    def test_disjoint_partition_and_identity_mutants(self):
        events = [
            event(13, 5),
            event(15, 12, 7, 2),
            event(16, 19, 15, 2),
            event(15, 24, 19, 0),
            event(16, 30, 27, 0),
            event(15, 39, 34, 1),
            event(16, 45, 40, 1),
            event(17, 52),
        ]
        self.assertEqual(m.chain(events), ([2, 3, 0, 3, 4, 1, 7], 15, 12))
        for which, changes in (
            (0, dict(worker=2)),
            (1, dict(gen=10)),
            (7, dict(ns=44)),
            (2, dict(begin=11)),
            (1, dict(component=1)),
        ):
            altered = list(events)
            altered[which] = altered[which]._replace(**changes)
            with self.assertRaises(ValueError):
                m.chain(altered)

    def test_grid_closed_and_open_ends(self):
        def fixture(maximum):
            def evaluate(n):
                return {"time_fits": n <= maximum, "units": n}

            return m.feasible_grid(evaluate, 100)

        self.assertIsNone(fixture(-1)["maximum_units"])
        self.assertEqual(fixture(100)["maximum_units"], 100)
        for n in (0, 45, 99):
            self.assertEqual(fixture(n)["last"]["units"], n)
            self.assertEqual(fixture(n)["first_over"]["units"], n + 1)

    def test_integer_break_point_on_constructed_worker_job(self):
        # With fixed base 10s−300ns and one 200ns SET, at most half of a
        # separate 200ns gap may remain; the hit is allowed to alias in RAM.
        job = m.base.Job((1, 1), 20, 200, True)
        ans = m.graded([[200]], [[job]], {job.key}, {job.key}, {"47": 0}, 10**10 - 300, 1)
        self.assertEqual(ans["maximum_units"], 5000)
        self.assertFalse(ans["first_over"]["time_fits"])
        # At 5001 the fractional bound exceeds 10s although the printed
        # rounded-down floor still says 10s.
        self.assertEqual(ans["first_over"]["first_floor_ns"], 10**10)
        self.assertTrue(ans["last"]["volume_fits"]["47"])


if __name__ == "__main__":
    unittest.main()
