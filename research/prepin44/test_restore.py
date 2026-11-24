import unittest

from restore import BYTES, execute, inspect_layer


class RestoreTests(unittest.TestCase):
    def test_cycle_and_one_external_scratch(self):
        a = execute([7, 5, 9], [5, 9, 7], scratch=False)
        b = execute([7, 5, 9], [5, 9, 7], scratch=True)
        self.assertEqual((a["gguf_loads"], a["local_copies"]), (1, 2))
        self.assertEqual(
            (b["gguf_loads"], b["local_copies"], b["extra_scratch_peak_bytes"]), (0, 4, BYTES)
        )

    def test_pending_load_is_an_internal_spare(self):
        a = execute([7, 5, 3, 2], [5, 7, 8, 3], scratch=True)
        self.assertEqual(
            (a["gguf_loads"], a["local_copies"], a["extra_scratch_peak_bytes"]), (1, 4, 0)
        )

    def test_empty_destinations_and_identity(self):
        self.assertEqual(execute([5, 7, -1], [-1, 5, 7], scratch=False)["local_copies"], 2)
        self.assertEqual(execute([5, 7], [5, 7], scratch=True)["local_copy_payload_bytes"], 0)

    def test_empty_slot_can_break_multiple_cycles(self):
        a = execute([1, 2, 3, 4, -1], [2, 1, 4, 3, -1], scratch=True)
        self.assertEqual(
            (a["gguf_loads"], a["local_copies"], a["extra_scratch_peak_bytes"]), (0, 6, 0)
        )

    def test_reject_inflight_duplicate_and_inverse(self):
        sl = dict(
            n_slots=2,
            n_expert=2,
            slot_expert=[0, 1],
            slot_state=[2, 2],
            slot_claimed=[0, 0],
            expert_slot=[0, 1],
        )
        for k, v in (
            ("slot_state", [1, 2]),
            ("slot_claimed", [1, 0]),
            ("slot_expert", [1, 1]),
            ("expert_slot", [1, 0]),
        ):
            with self.subTest(k=k), self.assertRaises(ValueError):
                inspect_layer(dict(sl, **{k: v}))


if __name__ == "__main__":
    unittest.main()
