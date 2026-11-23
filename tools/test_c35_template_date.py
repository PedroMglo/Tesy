"""Discriminants for the session-date request boundary."""

import unittest

from c2_gate import GateError
from c2_server_run import task_template_kwargs


class TemplateDateForwarding(unittest.TestCase):
    def test_frozen_value_forwarded(self):
        task = {'chat_template_kwargs': {'tesy_template_date': '2026-09-27'}}
        self.assertEqual(task_template_kwargs(task),
                         {'chat_template_kwargs': {'tesy_template_date': '2026-09-27'}})
        self.assertEqual(task_template_kwargs({}), {})

    def test_invalid_kwargs_rejected(self):
        for value in (None, [], {}, {1: '2026-09-27'}, {'x': float('inf')}):
            with self.subTest(value=value):
                with self.assertRaises((GateError, ValueError, TypeError)):
                    task_template_kwargs({'chat_template_kwargs': value})


if __name__ == '__main__':
    unittest.main()
