"""Bounded append-only request evidence and a sensor-independent deadline."""
import json
import os
import threading
import time


class Evidence:
    def __init__(self, path, request_id, started, timeout, cap=8*2**20):
        self.file = open(path, 'x')
        self.request_id = request_id
        self.started = started
        self.deadline = started + timeout
        self.cap = cap
        self.bytes = 0
        self.truncated = False
        self.write('REQUEST_START', deadline_monotonic=self.deadline)

    def write(self, kind, **data):
        row = dict(kind=kind, request_id=self.request_id,
                   monotonic_s=time.monotonic(), **data)
        encoded = json.dumps(row, allow_nan=False) + '\n'
        # Reserve terminal metadata, rather than silently losing the cap fence.
        if self.bytes + len(encoded.encode()) > self.cap - 2048:
            if not self.truncated:
                self.truncated = True
                self._append(json.dumps(dict(kind='EVIDENCE_TRUNCATED',
                    request_id=self.request_id, monotonic_s=time.monotonic(),
                    accepted=False, cap_bytes=self.cap))+'\n')
            raise ValueError('REQUEST_EVIDENCE_CAP_EXCEEDED')
        self._append(encoded)

    def _append(self, encoded):
        self.file.write(encoded); self.file.flush()
        self.bytes += len(encoded.encode())

    def close(self):
        if not self.file.closed:
            self.file.flush(); os.fsync(self.file.fileno()); self.file.close()


class Deadline:
    """Completion and timer share >= deadline convention and a locked fence."""
    def __init__(self, deadline, cancel, clock=time.monotonic):
        self.deadline = deadline
        self.cancel = cancel
        self.clock = clock
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.expired_at = None
        self.cancel_requested_at = None
        self.cancel_finished_at = None
        self.cancel_error = None
        self.thread = threading.Thread(target=self._watch, daemon=True)

    def start(self):
        self.thread.start()

    def check(self):
        with self.lock:
            if self.done.is_set() or self.clock() < self.deadline:
                return False
            self.expired_at = self.clock()
            self.cancel_requested_at = self.clock()
            self.done.set()
        try:
            self.cancel()
        except Exception as exc:
            self.cancel_error = f'{type(exc).__name__}:{exc}'
        finally:
            self.cancel_finished_at = self.clock()
        return True

    def _watch(self):
        while not self.done.wait(max(0, min(.025, self.deadline-self.clock()))):
            if self.check():
                break

    def complete(self, timestamp):
        # A complete late response is evidence even if cancellation ran first.
        with self.lock:
            valid = self.expired_at is None and timestamp < self.deadline
            if valid:
                self.done.set()
        if not valid:
            self.check()
        return valid

    def finish(self):
        self.done.set(); self.thread.join(timeout=5.3)
        return dict(deadline_monotonic=self.deadline,
                    expired_monotonic=self.expired_at,
                    cancel_requested_monotonic=self.cancel_requested_at,
                    cancel_finished_monotonic=self.cancel_finished_at,
                    cancel_error=self.cancel_error,
                    watchdog_alive=self.thread.is_alive())
