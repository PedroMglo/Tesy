"""Account for an incomplete private PFJ1 without admitting it to a latency analysis."""

import argparse
import collections
import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "pfj_incomplete", Path(__file__).with_name("analyse.py")
)
pfj = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pfj)


def inspect(path):
    with path.open("rb") as f:
        data = f.read(pfj.HEADER.size)
        report = {
            "qualification": "INCONCLUSIVE_INCOMPLETE_JOURNAL",
            "file_bytes": path.stat().st_size,
        }
        if len(data) != pfj.HEADER.size:
            return report | {"cause": "incomplete header"}
        magic, ver, width, cap, tried, saved, flags, res = pfj.HEADER.unpack(data)
        report.update(version=ver, saved=saved, attempted=tried, flags=flags)
        if (magic, ver, width, cap, res) != (b"TESYPF1\0", 1, pfj.RECORD.size, 262144, 0):
            return report | {"cause": "unrecognized geometry"}
        kinds = collections.Counter()
        zero = unknown = 0
        partial = 0
        for _ in range(cap):
            record = f.read(width)
            if len(record) != width:
                partial = len(record)
                break
            fields = pfj.Row(*pfj.RECORD.unpack(record))
            if not fields.ns and not any(fields):
                zero += 1
            elif 0 < fields.kind < len(pfj.NAMES):
                kinds[pfj.NAMES[fields.kind]] += 1
            else:
                unknown += 1
        report.update(
            observed_event_slots=dict(kinds),
            empty_slots=zero,
            unknown_slots=unknown,
            trailing_partial_bytes=partial,
            extra_bytes_after_capacity=max(0, path.stat().st_size - pfj.HEADER.size - cap * width),
            overflow_lower_bound=max(0, tried - cap),
            sealed=bool(flags & 1),
            native_invalid=bool(flags & 4),
        )
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("journal", type=Path)
    print(json.dumps(inspect(p.parse_args().journal), indent=2, sort_keys=True))
