import unittest

from screen import EXPERT, grade, replay


def serial(keys, start=0):
    return [(start + 2 * i, start + 2 * i + 1, k) for i, k in enumerate(keys)]


class InclusiveReadAdmission(unittest.TestCase):
    def test_equal_prior_frequency_bypasses_then_reuses(self):
        a, b = (0, 0), (25, 1)
        # a enters at its first P10. b has prior score 0/1/2 on three misses.
        # Strict comparison against a's score 1 admits only the third time.
        jobs = {"increment": serial([a, b, b, b]), "decode": serial([b], 10)}
        policy = replay(jobs, 1, "frequency_gate")
        inc = policy["increment"]["total"]
        dec = policy["decode"]["total"]
        self.assertEqual((inc["admissions"], inc["bypasses"], inc["hits"]), (2, 2, 0))
        self.assertEqual((inc["admissions_reused_by_F"], dec["hits"], dec["nvme_reads"]), (1, 1, 0))
        self.assertEqual(inc["host_copy_on_admission_bytes"], 2 * EXPERT)
        self.assertEqual(dec["hit_to_private_staging_bytes"], EXPERT)
        self.assertEqual(dec["primary_h2d_payload_bytes"], EXPERT)

    def test_residency_begins_at_publication_not_lookup(self):
        a, b = (0, 0), (0, 1)
        jobs = {"increment": [(0, 4, a), (1, 2, b)], "decode": [(5, 6, a)]}
        always = replay(jobs, 1, "always_lru")
        self.assertEqual(always["decode"]["total"]["hits"], 1)
        self.assertEqual(always["increment"]["total"]["admissions_unused_by_F"], 1)

    def test_evict_inflight_hit_uses_its_private_staging(self):
        a, b = (0, 0), (0, 1)
        jobs = {"increment": serial([a]), "decode": [(3, 7, a), (4, 5, b), (8, 9, b)]}
        always = replay(jobs, 1, "always_lru")
        self.assertEqual(always["decode"]["total"]["hits"], 2)
        self.assertEqual(always["decode"]["total"]["admissions"], 1)

    def test_reject_same_key_claimed_twice(self):
        a = (0, 0)
        with self.assertRaises(ValueError):
            replay({"increment": [(0, 5, a), (1, 4, a)], "decode": []}, 1, "always_lru")

    def test_tie_break_by_recency_and_payload_conservation(self):
        a, b, c = (0, 0), (0, 1), (25, 0)
        seq = [a, b, c, c, c, a, b, b]
        jobs = {"increment": serial(seq[:5]), "decode": serial(seq[5:], 11)}
        p = replay(jobs, 2, "frequency_gate")
        lru = replay(jobs, 2, "always_lru")
        self.assertEqual(p["decode"]["total"]["hits"], 2)
        self.assertFalse(grade(p, p)["decode_beats_lru"])
        for v in (p, lru):
            for phase in v.values():
                s = phase["total"]
                self.assertEqual(s["lookups"], s["hits"] + s["nvme_reads"])
                self.assertEqual(
                    s["admissions"], s["admissions_reused_by_F"] + s["admissions_unused_by_F"]
                )
