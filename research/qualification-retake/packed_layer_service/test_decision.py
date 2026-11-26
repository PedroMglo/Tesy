import copy
import unittest

from decision import schedule, screen


def arms():
    return [
        dict(
            block=b,
            layout=layout,
            observer=m,
            publish_ns=90 if layout == "DIRECT" else 100,
            resume_ns=94 if layout == "DIRECT" else 105,
            outer_ns=120,
        )
        for b, layout, m in schedule()
    ]


class Decision(unittest.TestCase):
    def test_complete_design(self):
        a = arms()
        self.assertEqual(len(a), 36)
        self.assertEqual(screen(a)["decision"], "GO_NEXT_SERVICE_SCOPE")
        self.assertEqual(screen(a)["detail_class"], "QUALIFIED_DETAIL")
        for x in (a[:-1], a[::-1], [a[0]] + a[:-1]):
            with self.assertRaises(ValueError):
                screen(x)

    def test_detail_is_not_primary(self):
        a = arms()
        for row in a:
            if row["observer"] == "DETAIL" and row["layout"] == "DENSE":
                row["outer_ns"] = 150
        r = screen(a)
        self.assertEqual(r["decision"], "GO_NEXT_SERVICE_SCOPE")
        self.assertEqual(r["detail_class"], "DIAGNOSTIC_PERTURBED_DETAIL")

    def test_control_and_resume_protection(self):
        for metric in ["publish_ns", "resume_ns"]:
            a = arms()
            for row in a:
                if row["layout"] == "STAGED":
                    row[metric] = 85
            self.assertTrue(screen(a)["decision"].startswith("NO_GO"))

    def test_nonpositive_and_thresholds(self):
        a = arms()
        x = copy.deepcopy(a)
        x[0]["outer_ns"] = 0
        with self.assertRaises(ValueError):
            screen(x)
        for row in a:
            if row["layout"] == "DIRECT":
                row["publish_ns"] = 95
        self.assertEqual(screen(a)["decision"], "GO_NEXT_SERVICE_SCOPE")
        for row in a:
            if row["layout"] == "DIRECT" and row["block"] in (1, 2):
                row["publish_ns"] = 100
        self.assertTrue(screen(a)["decision"].startswith("NO_GO"))
