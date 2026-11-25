import unittest

from screen import compare


def example(body):
    return [(3, b"<|channel|>"), (1, b"analysis"), (3, b"<|message|>"), (1, body)]


class PrefixTests(unittest.TestCase):
    def test_stable_difference_space(self):
        state = compare(example(b" A"), {"reasoning_content": "A"})
        self.assertEqual(
            (state["class"], state["first_difference_zero_based"]), ("visible_prefix_diverges", 0)
        )

    def test_prefix_only(self):
        self.assertEqual(
            compare(example(b" A"), {"reasoning_content": " A trailing"})["class"],
            "prefix_visible_equal",
        )

    def test_ambiguous(self):
        for parts in (
            example(b" "),
            example(b"a<"),
            example(b"\xe2"),
            example(b"A")[:2],
            [(1, b"<|channel|>")] + example(b"A")[1:],
        ):
            self.assertEqual(compare(parts, {})["class"], "INCONCLUSIVE")

    def test_no_cross_channel(self):
        parts = example(b"z")
        parts[1] = (1, b"final")
        self.assertEqual(
            compare(parts, {"content": "zz", "reasoning_content": "x"})["channel"], "content"
        )
