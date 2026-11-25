import unittest

import screen


class NominalInputTests(unittest.TestCase):
    def test_render_first_byte_only(self):
        with self.assertRaises(screen.Mismatch) as ctx:
            screen.same("T2_stock_render", b"fixture X", b"fixture Y")
        self.assertEqual(ctx.exception.detail["first_difference_zero_based"], 8)
        self.assertEqual(ctx.exception.detail["unit"], "byte")
        self.assertNotIn("fixture", str(ctx.exception.detail))

    def test_vector_tail_and_equal_counts(self):
        for actual, pos in [([2, 3], 2), ([2, 3, 7], 2)]:
            with self.assertRaises(screen.Mismatch) as ctx:
                screen.same("T1_C269_ids", [2, 3, 4], actual, "id")
            self.assertEqual(ctx.exception.detail["first_difference_zero_based"], pos)
        self.assertIsNone(screen.same("T1_stock_ids", [2, 3, 4], [2, 3, 4], "id"))

    def test_nested_frames_and_private_text_order(self):
        payload = [
            {"role": "user", "content": "example"},
            {"role": "assistant", "content": "12345"},
            {"role": "user", "content": "repeat"},
        ]
        self.assertEqual(
            screen.fields(screen.messages_bytes(payload)),
            [b"user", b"example", b"assistant", b"12345", b"user", b"repeat"],
        )
        with self.assertRaises(ValueError):
            screen.fields(screen.frame(b"example")[:-1])


if __name__ == "__main__":
    unittest.main()
