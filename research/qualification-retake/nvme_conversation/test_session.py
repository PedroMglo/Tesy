import os
import socket
import unittest

from contract import ids_hash, owned_listener


class TestProvenance(unittest.TestCase):
    def test_listener_is_owned_by_process(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            self.assertTrue(owned_listener(os.getpid(), port).isdigit())
            with self.assertRaisesRegex(ValueError, "another PID"):
                owned_listener(os.getppid(), port)
        with self.assertRaisesRegex(ValueError, "absent"):
            owned_listener(os.getpid(), port)

    def test_ids_are_binary_int32(self):
        self.assertNotEqual(ids_hash([3, 4]), ids_hash([4, 3]))
        with self.assertRaisesRegex(ValueError, "invalid"):
            ids_hash([True])


if __name__ == "__main__":
    unittest.main()
