import itertools
import math
import unittest

from screen import log2_bounds, stream_bound


def encode(x, letter, frequencies, ratio, radix):
    mass, f = sum(frequencies), frequencies[letter]
    digits = []
    while x >= radix * ratio * f:
        digits.append(x % radix)
        x //= radix
    return (x // f) * mass + sum(frequencies[:letter]) + x % f, digits


def decode(x, digits, frequencies, ratio, radix):
    mass = sum(frequencies)
    prefix = 0
    for letter, f in enumerate(frequencies):
        if prefix <= x % mass < prefix + f:
            x = (x // mass) * f + x % mass - prefix
            while x < ratio * mass:
                x = x * radix + digits.pop()
            return x, letter
        prefix += f
    raise AssertionError("invalid symbol")


class MarginalRans(unittest.TestCase):
    def test_all_toy_steps_and_words(self):
        for frequencies, ratio, radix in [([1, 2, 5], 2, 2), ([1, 2, 4], 4, 4)]:
            mass = sum(frequencies)
            lower = mass * ratio
            for initial in range(lower, radix * lower):
                for word in itertools.product(range(3), repeat=4):
                    x, digits = initial, []
                    for letter in word:
                        prev = x
                        x, emitted = encode(x, letter, frequencies, ratio, radix)
                        digits.extend(emitted)
                        self.assertTrue(lower <= x < radix * lower)
                        self.assertGreaterEqual(
                            radix ** len(emitted) * x * frequencies[letter] * ratio,
                            prev * mass * (ratio - 1),
                        )
                    information = sum(math.log2(len(word) / word.count(s)) for s in word)
                    self.assertGreaterEqual(
                        len(digits) * math.log2(radix),
                        information - len(word) * math.log2(ratio / (ratio - 1)) - math.log2(radix),
                    )
                    for expected in reversed(word):
                        x, s = decode(x, digits, frequencies, ratio, radix)
                        self.assertEqual(s, expected)
                    self.assertEqual((x, digits), (initial, []))

    def test_frozen_byte_parameters(self):
        frequencies, word, ratio, radix = [1, 2, 5], [0, 0, 2, 1, 2, 1, 0] * 8, 256, 256
        counts = [word.count(i) for i in range(3)]
        bound = stream_bound(counts, 3, len(word))[2]
        lower = ratio * sum(frequencies)
        for initial in (lower, lower + 1, radix * lower - 1):
            x, digits = initial, []
            for s in word:
                x, emitted = encode(x, s, frequencies, ratio, radix)
                digits.extend(emitted)
            self.assertGreaterEqual(8 * len(digits), bound)

    def test_constant_and_uniform(self):
        self.assertEqual(log2_bounds(1), (0, 0))
        self.assertEqual(stream_bound([256, 0], 2, 256), (0, 0, 0))
        lo, hi, bits = stream_bound([128, 128], 2, 256)
        self.assertEqual((lo, hi), (256 * 10**9, 256 * 10**9))
        self.assertEqual(bits, 247)

    def test_bad_population(self):
        for counts in ([True, 1], [-1, 3], [1.0, 1], [1, 2], [2]):
            with self.assertRaises(ValueError):
                stream_bound(counts, 2, 2)
