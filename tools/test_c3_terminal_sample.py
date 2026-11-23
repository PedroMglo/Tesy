#!/usr/bin/env python3
"""Model-free checks for the server monitor's terminal /proc race rule."""

import subprocess
import unittest

from c2_server_run import child_exited_after_sample_loss


class FakeChild:
    def __init__(self, exited):
        self.exited = exited
        self.waited = False

    def wait(self, timeout):
        assert timeout == 0.2
        self.waited = True
        if not self.exited:
            raise subprocess.TimeoutExpired("fake-child", timeout)
        return 0


class TerminalSampleTest(unittest.TestCase):
    def test_confirmed_exit_can_skip_terminal_partial_sample(self):
        child = FakeChild(True)
        self.assertTrue(child_exited_after_sample_loss(child))
        self.assertTrue(child.waited)

    def test_live_process_must_fail_closed(self):
        child = FakeChild(False)
        self.assertFalse(child_exited_after_sample_loss(child))
        self.assertTrue(child.waited)


if __name__ == "__main__":
    unittest.main()
