import unittest

from selection import NAMES, before_decode, boundary, memberships


def empty_snapshot():
    return dict(
        pending_queue=0,
        layers=[
            dict(
                layer=layer,
                slot_expert=[-1] * 40,
                slot_generation=[0] * 40,
                slot_state=[0] * 40,
                slot_claimed=[0] * 40,
            )
            for layer in range(36)
        ],
    )


def prefix():
    def event(kind, layer=-1, expert=-1, slot=-1, gen=0, c=-1, size=0, width=0, route=0):
        return (
            " ".join(map(str, (kind, 1, 0, route, layer, expert, slot, gen, c, size, width))) + "\n"
        )

    rows = [boundary.HEADER + "\n", event(15)]
    for layer in range(36):
        for n, width in enumerate([32, 32, 32, 32, 25] if layer < 35 else [1]):
            route = 1 + layer * 5 + n
            rows.append(event(2, layer, route=route, width=width))
            if layer == 35:
                rows.extend(event(3, layer, e, route=route) for e in range(4))
    rows.append(event(16))
    return rows


class TestCausalCut(unittest.TestCase):
    def test_first_decode_row_is_inaccessible(self):
        def fail_if_suffix_is_touched():
            yield from prefix()
            raise AssertionError("selection read a future row")

        r = before_decode(fail_if_suffix_is_touched(), empty_snapshot())
        self.assertEqual(r["reload_twice"], [])
        self.assertEqual(r["P3_observations_0_to_34"], 0)
        self.assertEqual(r["P3_observations_35"], 4)

    def test_one_tile_is_one_publication_signal(self):
        pools = [{2}] + [set() for _ in range(35)]
        broad, last, path = memberships(
            {(0, 1): {0, 2}, (0, 2): {0, 4}, (0, 3): {0}, (1, 4): {2, 4}}, pools
        )
        self.assertEqual(broad, [[0, 1], [1, 4]])
        self.assertEqual(last, [[1, 4]])
        self.assertEqual(path, [[0, 1, [0, 2]], [1, 4, [2, 4]]])
        self.assertEqual(len(NAMES), 4)

    def test_tracks_real_generation_identity_and_eviction_by_tile(self):
        rows = prefix()
        for expert, route, gen in ((7, 1, 1), (8, 2, 2), (7, 3, 3), (9, 4, 4)):
            start = (
                next(
                    i
                    for i, row in enumerate(rows)
                    if row.split()[0:5] == ["2", "1", "0", str(route), "0"]
                )
                + 1
            )
            phases = (
                [(-1, 4), (-1, 5)]
                + [(component, step) for component in range(3) for step in (6, 7, 8, 9)]
                + [(-1, 10)]
            )
            rows[start:start] = [
                f"{step} 1 0 {route} 0 {expert} 0 {gen} {c} {4406400 if c >= 0 else 0} 0\n"
                for c, step in phases
            ]
        r = before_decode(iter(rows), empty_snapshot())
        self.assertEqual(r["qualifying_tiles"], [[0, 7, [0, 2]]])
        self.assertEqual(r["initial_residents"][0], [9])
        self.assertEqual(r["reload_last"], [])
        i = next(i for i, line in enumerate(rows) if line.startswith("10 "))
        rows[i] = rows[i].replace("10 1 0 1", "10 1 0 2", 1)
        with self.assertRaises(ValueError):
            before_decode(iter(rows), empty_snapshot())

    def test_missing_cut_and_geometry_rejected(self):
        rows = prefix()
        for invalid in (rows[:-1], rows[:3] + rows[4:]):
            with self.assertRaises(ValueError):
                before_decode(iter(invalid), empty_snapshot())
