import errno
import unittest

import audit

Row = audit.pfj["Row"]


def event(kind, ns, **kwargs):
    base = dict.fromkeys(Row._fields, 0)
    base.update(
        worker=2,
        layer=0,
        expert=0,
        slot=6,
        gen=1,
        call=1,
        tile=1,
        wave=-1,
        component=-1,
        fd=5,
        ns=ns,
        kind=kind,
    )
    return Row(**(base | kwargs))


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.files = {29: event(29, 1), 7: event(7, 1, fd=3)}
        self.events = [
            event(13, 11),
            event(30, 13, begin=12, b=audit.WINDOW, c=-1, error=errno.EINTR),
            event(30, 15, begin=14, b=audit.WINDOW, c=audit.WINDOW),
            *[
                event(
                    16,
                    17 + k * 2,
                    begin=16 + k * 2,
                    component=k,
                    a=audit.SLAB,
                    b=6 * audit.SLAB,
                    c=k * audit.SLAB,
                )
                for k in range(3)
            ],
            event(17, 24),
        ]

    def service(self, events, short=False):
        return audit.check_job(events, packed=True, short=short, files=self.files, weights={})

    def test_packed_and_fault(self):
        reads, copies = self.service(self.events)
        self.assertEqual((len(reads), len(copies)), (2, 3))
        short = self.events[2]._replace(c=3 * audit.SLAB - 1)
        reads, copies = self.service([self.events[0], short, event(18, 20)], short=True)
        self.assertEqual((len(reads), len(copies)), (1, 0))

    def test_reject_corrupted_delivery(self):
        for index, change in [
            (1, {"error": errno.EIO}),
            (2, {"fd": 3}),
            (2, {"a": audit.STRIDE}),
            (2, {"c": 3 * audit.SLAB - 1}),
            (3, {"component": 1}),
            (4, {"b": 0}),
            (4, {"begin": 13}),
            (5, {"c": 0}),
            (6, {"kind": 18}),
        ]:
            with self.subTest(index=index, change=change), self.assertRaises(ValueError):
                damaged = self.events[:]
                damaged[index] = damaged[index]._replace(**change)
                self.service(damaged)
        with self.assertRaises(ValueError):
            self.service(self.events[:4] + self.events[5:])


if __name__ == "__main__":
    unittest.main()
