#!/usr/bin/env python3
"""Harmless HTTP process for the prospective c2 launch gate smoke."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import signal
import sys


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            row = {"status": "ok"}
        elif self.path == "/v1/models":
            row = {"data": [{"id": "c120-model-free-smoke"}]}
        else:
            self.send_error(404)
            return
        data = json.dumps(row).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


def main():
    server = HTTPServer(("127.0.0.1", 18367), Handler)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    server.serve_forever()


if __name__ == "__main__":
    main()
