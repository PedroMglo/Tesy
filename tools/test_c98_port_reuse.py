"""Reproduce C97's TIME_WAIT prelaunch false positive without loading a model."""

import errno
import socket
import unittest


class PortReuse(unittest.TestCase):
    def test_time_wait_needs_reuse_on_next_bind(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
            listener.listen(1)
            with socket.create_connection(('127.0.0.1', port)) as client:
                accepted, _ = listener.accept()
                accepted.close()  # Server side enters TIME_WAIT after client closes.
        with socket.socket() as no_reuse:
            with self.assertRaises(OSError) as error:
                no_reuse.bind(('127.0.0.1', port))
            self.assertEqual(error.exception.errno, errno.EADDRINUSE)
        with socket.socket() as reused:
            reused.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            reused.bind(('127.0.0.1', port))


if __name__ == '__main__':
    unittest.main()
