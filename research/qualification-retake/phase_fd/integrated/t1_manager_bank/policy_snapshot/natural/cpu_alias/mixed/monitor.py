"""Identify the live GPU owner's lifecycle from the acquisition monitor itself."""

import hashlib
import json


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def monitoring(path, expected_sha):
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected_sha, "monitor checksum")
    rows = [json.loads(line) for line in raw.splitlines()]
    require(len(rows) >= 4, "incomplete monitor")
    require(
        rows[0]["phase"] == "entry" and rows[-1]["phase"] == "after_exit", "incomplete acquisition"
    )
    stages = [v for v in rows if v["phase"] != "periodic"]
    require(
        [v["phase"] for v in stages] == ["entry", "active", "finish", "after_exit"],
        "owner handoff sequence",
    )
    owners = [v["observation"]["gpu_owners"] for v in stages]
    require(
        owners[0] == owners[3] == []
        and len(owners[1]) == 1
        and isinstance(owners[1][0], int)
        and owners[1][0] > 0
        and owners[1] == owners[2],
        "owner at handoff",
    )
    previous = -1
    for v in rows:
        require(previous < v["elapsed_s"] <= previous + 5.0, "monitor gap")
        previous = v["elapsed_s"]
        require(
            0 < v["peak_bytes"] < 1856 << 20 and 0 <= v["observation"]["gpu"]["used_mib"] < 1536,
            "resource cap",
        )
        if v["phase"] == "periodic" and v["stage"] == 2:
            require(v["observation"]["gpu_owners"] == owners[1], "owner lost during compute")
    return rows
