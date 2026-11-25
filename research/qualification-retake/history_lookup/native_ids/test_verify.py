import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "native_event_verifier", Path(__file__).with_name("verify.py")
)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

GEOMETRY = [(11, 0, 2, 0), (17, 10, 2, 0)]


def record(stamp, level, name, task, message):
    return b"0.00.000.%03d %s slot %12.12s: id  0 | task %d | %s\n" % (
        stamp,
        level,
        name,
        task,
        message,
    )


def fixture():
    raw = bytearray()
    for i, task in enumerate([0, 9]):
        n = GEOMETRY[i][0]
        raw += record(
            1 + i * 10, b"I", b"launch_slot_with_task", task, b"processing task, is_child = 0"
        )
        raw += record(
            2 + i * 10,
            b"D",
            b"process_token",
            task,
            b"n_decoded = 1, n_remaining = 255, next token:    37 'a\n\xe2'",
        )
        raw += record(
            3 + i * 10,
            b"D",
            b"handle_last_sampled_token",
            task,
            b"slot decode token, id=37, n_ctx = 8192, n_tokens = %d, truncated = 0" % n,
        )
        raw += record(4 + i * 10, b"D", b"process_token", task, b"stopped by EOS")
        raw += record(
            5 + i * 10,
            b"D",
            b"process_token",
            task,
            b"n_decoded = 2, n_remaining = 254, next token: 20001 ''",
        )
        raw += record(
            6 + i * 10,
            b"I",
            b"release",
            task,
            b"stop processing: n_tokens = %d, truncated = 0" % (n + 1),
        )
    return bytes(raw)


class NativeEvents(unittest.TestCase):
    def test_two_complete(self):
        log = fixture()
        turns = v.trajectories(log, GEOMETRY)
        self.assertEqual([[t for t, _ in rows] for rows in turns], [[37, 20001]] * 2)
        for rows in turns:
            v.piece_rows(log, rows, [b"a\n\xe2", b"\x00x"])
        self.assertEqual(v.ids_bytes([37, 20001]), b"\x25\0\0\0\x21\x4e\0\0")

    def test_state_corruption(self):
        raw = fixture()
        for old, new in [
            (b"next token:    37", b"next token: 0037"),
            (b"next token:    37", b"next token:    38"),
            (b"n_tokens = 11,", b"n_tokens = 12,"),
            (b"stopped by EOS", b"stopped by limit"),
            (b"000.005 D", b"000.002 D"),
            (b"task 0 | n_decoded", b"task 1 | n_decoded"),
            (b"n_remaining = 255", b"n_remaining = 223"),
            (b"D slot process_toke: id  0", b"D slot process_toke: id  1"),
            (b"stop processing: n_tokens = 12", b"stop processing: n_tokens = 13"),
        ]:
            with self.subTest(old=old, new=new), self.assertRaises(v.Gate):
                v.trajectories(raw.replace(old, new, 1), GEOMETRY)

    def test_multiline_spurious_marker(self):
        original = fixture()
        fake = record(
            2,
            b"D",
            b"process_token",
            0,
            b"n_decoded = 1, n_remaining = 255, next token:    37 'decoy'",
        )
        with self.assertRaises(v.Gate):
            v.trajectories(original.replace(b"a\n\xe2", b"a\n" + fake + b"\xe2", 1), GEOMETRY)
        with self.assertRaises(v.Gate):
            v.trajectories(fake + original, GEOMETRY)
        # A token may contain words from the logger without a native header.
        raw = original.replace(b"a\n\xe2", b"a\nn_decoded = 1\n", 1)
        samples = v.trajectories(raw, GEOMETRY)
        v.piece_rows(raw, samples[0], [b"a\nn_decoded = 1\n", b""])
        with self.assertRaises(v.Gate):
            v.piece_rows(raw, samples[0], [b"a", b""])

    def test_extra_task_and_bad_size(self):
        with self.assertRaises(v.Gate):
            v.trajectories(fixture() + fixture(), GEOMETRY)
        with self.assertRaises(v.Gate):
            v.ids_bytes([True])
