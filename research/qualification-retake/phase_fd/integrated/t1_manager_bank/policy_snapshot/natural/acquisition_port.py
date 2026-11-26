"""Wait for the E20 control's closed TCP sockets to release the original C281 bind."""

import errno
import subprocess
import time
from collections import Counter
from pathlib import Path

LIMIT = 75


def sockets(port):
    states = []
    for path in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        for line in path.read_text().splitlines()[1:]:
            fields = line.split()
            if int(fields[1].split(":")[1], 16) == port:
                states.append(fields[3])
    return states


def verify_owner(unit, pid):
    state = subprocess.check_output(
        ["systemctl", "--user", "show", unit + ".service", "-p", "ActiveState", "--value"],
        text=True,
        timeout=5,
    ).strip()
    if state != "inactive" or pid <= 1 or Path(f"/proc/{pid}").exists():
        raise ValueError("previous C281 unit/PID has not exited")


def transition(probe, port, owner, log, observe=sockets, now=time.monotonic, sleep=time.sleep):
    start = now()
    log.update(limit_s=LIMIT, samples=[], bind_available=False)
    while True:
        owner()
        elapsed = now() - start
        if elapsed > LIMIT:
            raise TimeoutError("C281 strict bind deadline")
        states = observe(port)
        log["samples"].append({"elapsed_s": elapsed, "tcp_states": dict(Counter(states))})
        if any(state != "06" for state in states):
            raise ValueError("another TCP state is present before C281 bind")
        try:
            probe()
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE or not states:
                raise
            remaining = LIMIT - (now() - start)
            if remaining <= 0:
                raise TimeoutError("C281 TIME_WAIT deadline") from exc
            sleep(min(1, remaining))
        else:
            if now() - start > LIMIT:
                raise TimeoutError("C281 strict bind deadline")
            log.update(elapsed_s=now() - start, bind_available=True)
            return
