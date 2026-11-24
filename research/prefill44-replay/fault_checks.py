"""Reject deliberate changes to authenticated C163-ON1 evidence in memory only."""

from copy import deepcopy

from replay import need, replay


def fault_checks(initial, final, rows, routing):
    failures = {}

    def reject(name, fragment, args):
        try:
            replay(*args)
        except ValueError as exc:
            need(fragment in str(exc), f"unexpected fault {name}: {exc}")
            failures[name] = str(exc)
        else:
            raise ValueError(f"fault accepted: {name}")

    changed = rows.copy()
    index = next(i for i, row in enumerate(rows) if row["kind"] == "EVICT")
    changed[index] = dict(rows[index], slot=(rows[index]["slot"] + 1) % 44)
    reject("victim_slot", "expected", (initial, final, changed, routing))

    changed = routing.copy()
    index = next(i for i, route in enumerate(routing) if route["call_id"] == 10)
    ids = list(changed[index]["ids"])
    ids[0], ids[1] = ids[1], ids[0]
    changed[index] = dict(changed[index], ids=ids)
    reject("route_rank", "expected", (initial, final, rows, changed))

    for field in ("pool_used", "slot_last_use", "route_hotness"):
        changed = deepcopy(final)
        values = changed["layers"][0][field]
        values[0] = (values[0] + 1) % 44 if field == "pool_used" else values[0] + 1
        reject("snapshot_" + field, "final layer 0 " + field, (initial, changed, rows, routing))
    return failures
