"""Replay the C156 controller from routed IDs and immutable warm cache state."""

from collections import Counter, deque
from copy import deepcopy

from c152_snapshot_read import VECTORS


def need(test, reason):
    if not test:
        raise ValueError(reason)


def victim(sl):
    eligible = [s for s in range(sl["n_slots"]) if not sl["keep"][s] and sl["slot_state"][s] != 1]
    return min(
        eligible,
        key=lambda s: (
            (0,)
            if sl["slot_state"][s] == 0
            else (1, sl["route_hotness"][sl["slot_expert"][s]], sl["slot_last_use"][s], s)
        ),
        default=-1,
    )


def touch(sl, slot):
    sl["use_counter"] += 1
    sl["slot_last_use"][slot] = sl["use_counter"]


def emit_wave(sl, ids, wave):
    """Two native passes per token, real ranks first and distinct parking afterwards."""
    for offset in range(0, len(ids), 4):
        group = ids[offset : offset + 4]
        used = []
        for expert in group:
            if sl["expert_wave"][expert] == wave:
                slot = sl["expert_slot"][expert]
                need(slot >= 0 and sl["slot_state"][slot] == 2, "unready selected expert")
                touch(sl, slot)
                used.append(slot)
        for slot in sl["plan_pool"]:
            if len(used) == 4:
                break
            if slot not in used:
                need(sl["slot_state"][slot] == 2, "unready parking slot")
                used.append(slot)
        need(len(used) == len(set(used)) == 4, "parking cardinality")
        sl["pool_used"] = used


class Controller:
    def __init__(self, initial):
        self.s = deepcopy(initial)
        # No inherited worker, queue or outstanding generation in these cut points.
        need(not initial["queue"] and not any(w["phase"] for w in initial["owned"]), "nonidle seed")
        self.queue, self.events = deque(), deque()
        self.owners = {}
        self.count = Counter()
        self.route = None
        self.started = self.waiting = False

    def begin_route(self, route):
        need(self.route is None and not self.events, "overlapping routed blocks")
        self.route = route
        self.sl = sl = self.s["layers"][route["layer"]]
        self.s["n_calls"] += 1
        need(self.s["n_calls"] == route["n_calls"], "global route clock")
        sl["uniq"] = list(dict.fromkeys(route["ids"]))
        sl["touched"] = [int(e in sl["uniq"]) for e in range(sl["n_expert"])]
        if route["mode"] == 1:
            cap = sl["plan_capacity"]
            sl["expert_wave"] = [255] * sl["n_expert"]
            for index, expert in enumerate(sl["uniq"]):
                sl["expert_wave"][expert] = index // cap
            sl["n_waves"] = (len(sl["uniq"]) + cap - 1) // cap
            sl["next_wave"] = 0
            self.wave = 0
            self.total = (min(sl["n_expert"], len(route["ids"])) + cap - 1) // cap
        else:
            self.wave = -1
            hot = sl["route_hotness"]
            for expert in sl["uniq"]:
                if hot[expert] < 2**32 - 2:
                    hot[expert] += 1
            interval = self.s["hot_decay_interval"]
            if interval and self.s["n_calls"] % interval == 0:
                for layer in self.s["layers"]:
                    layer["route_hotness"] = [x >> 1 for x in layer["route_hotness"]]
        self.count["routes"] += 1

    def expect(self, kind, **fields):
        self.events.append(
            dict(kind=kind, call_id=self.route["call_id"], layer=self.sl["layer"], **fields)
        )

    def enqueue(self, expert, slot):
        self.s["next_work_id"] += 1
        key = (
            self.route["call_id"],
            self.sl["layer"],
            expert,
            slot,
            self.sl["slot_gen"][slot],
            self.s["next_work_id"],
        )
        self.queue.append(key)
        self.expect("ENQUEUE", expert=expert, slot=slot, generation=key[4], work_id=key[5])

    def reserve(self, expert, slot):
        sl = self.sl
        prev = sl["slot_expert"][slot]
        if prev >= 0:
            self.expect(
                "EVICT",
                expert=prev,
                slot=slot,
                victim=expert,
                state=sl["slot_state"][slot],
                generation=sl["slot_gen"][slot],
            )
            sl["expert_slot"][prev] = -1
        sl["slot_expert"][slot] = expert
        sl["slot_state"][slot] = 1
        sl["slot_gen"][slot] += 1
        sl["expert_slot"][expert] = slot
        sl["seen"][expert] = 1
        touch(sl, slot)
        self.expect("RESERVE", expert=expert, slot=slot, generation=sl["slot_gen"][slot], state=1)

    def admissions(self):
        sl, w, uniq = self.sl, self.wave, self.sl["uniq"]
        sl["keep"] = [0] * sl["n_slots"]
        sl["demand_slots"] = []
        self.borrowed = []
        here, upcoming = uniq, []
        width = len(self.route["ids"]) // 4
        if w != -1:
            cap = sl["plan_capacity"]
            here = uniq[w * cap : (w + 1) * cap]
            upcoming = uniq[(w + 1) * cap : (w + 2) * cap]
            self.borrowed = sl["plan_pool"][: max(0, 4 - len(here))]
            need(len(self.borrowed) == max(0, 4 - len(here)), "incomplete parking prefix")
            for slot in self.borrowed:
                sl["keep"][slot] = 1
            for expert in upcoming:
                slot = sl["expert_slot"][expert]
                if slot >= 0:
                    sl["keep"][slot] = 1
        waited = False
        for expert in here:
            slot = sl["expert_slot"][expert]
            state = 0 if slot < 0 else sl["slot_state"][slot]
            self.expect(
                "DEMAND",
                expert=expert,
                slot=slot,
                state=state,
                generation=0 if slot < 0 else sl["slot_gen"][slot],
                wave=w,
                n_tokens=width,
            )
            if state == 0:
                slot = victim(sl)
                need(slot >= 0, "requires victim-wait replay")
                self.reserve(expert, slot)
            if state != 2:
                self.enqueue(expert, slot)
                waited = True
            sl["keep"][slot] = 1
            sl["demand_slots"].append(slot)
        for expert in upcoming:
            if sl["expert_slot"][expert] >= 0:
                continue
            slot = victim(sl)
            if slot < 0:
                continue
            self.reserve(expert, slot)
            self.expect(
                "PRELOAD",
                expert=expert,
                slot=slot,
                wave=w + 1,
                state=1,
                generation=sl["slot_gen"][slot],
                n_tokens=width,
            )
            sl["keep"][slot] = 1
            self.enqueue(expert, slot)
        self.waiting = waited
        if waited:
            for slot in sl["demand_slots"]:
                self.expect(
                    "BARRIER_SLOT",
                    expert=sl["slot_expert"][slot],
                    slot=slot,
                    wave=w,
                    generation=sl["slot_gen"][slot],
                    state=sl["slot_state"][slot],
                )
            self.expect("WAIT_BEGIN", wave=w)
        self.started = True

    def consume(self, row):
        kind = row["kind"]
        if not self.started and kind in ("DEMAND", "RESERVE", "EVICT", "WAVE_DONE", "REMAP_DONE"):
            need(self.route is not None, "wave outside route")
            self.admissions()
        if self.events:
            expected = self.events.popleft()
            need(
                all(row[k] == v for k, v in expected.items()),
                f"expected {expected} observed {kind} at seq {row['seq']}",
            )
        elif kind in ("DEQUEUE", "STALE_WORK", "RESIDENT_COMMIT"):
            self.worker(row)
        elif kind == "WAIT_END":
            need(
                self.waiting
                and row["wave"] == self.wave
                and all(self.sl["slot_state"][s] == 2 for s in self.sl["demand_slots"]),
                "barrier return without ready constituents",
            )
            self.waiting = False
        elif kind in ("REMAP_DONE", "WAVE_DONE"):
            need(
                self.started
                and not self.waiting
                and row["layer"] == self.sl["layer"]
                and row["wave"] == self.wave
                and row["n_tokens"] == len(self.route["ids"]) // 4,
                "incomplete wave or geometry",
            )
            sl = self.sl
            if self.wave == -1:
                need(kind == "REMAP_DONE", "normal remap boundary")
                for expert in self.route["ids"]:
                    slot = sl["expert_slot"][expert]
                    need(slot >= 0 and sl["slot_state"][slot] == 2, "remap payload missing")
                    touch(sl, slot)
                self.route = None
            else:
                need(kind == "WAVE_DONE", "wave boundary")
                sl["plan_pool"] = sl["demand_slots"] + self.borrowed
                sl["next_wave"] = self.wave + 1
                emit_wave(sl, self.route["ids"], self.wave)
                self.wave += 1
                if self.wave == self.total:
                    self.route = None
            self.started = False
        elif kind not in (
            "CALL_BEGIN",
            "CALL_END",
            "MUTEX_WAIT_BEGIN",
            "MUTEX_WAIT_END",
            "LOAD_BEGIN",
            "LOAD_END",
            "READ_BEGIN",
            "READ_END",
            "TENSOR_SET_BEGIN",
            "TENSOR_SET_RETURN",
        ):
            raise ValueError(f"unexpected {kind} at seq {row['seq']}")
        self.count[kind] += 1

    def worker(self, row):
        sl = self.s["layers"][row["layer"]]
        kind, slot, worker = row["kind"], row["slot"], row["component"]
        key = tuple(row[k] for k in ("call_id", "layer", "expert", "slot", "generation", "work_id"))
        need(0 <= worker < self.s["workers"], "unidentified worker")
        if kind == "RESIDENT_COMMIT":
            need(
                self.owners.pop(worker, None) == key and sl["slot_claimed"][slot], "unowned commit"
            )
            sl["slot_claimed"][slot] = 0
            sl["slot_state"][slot] = 2
            return
        need(
            self.queue and self.queue.popleft() == key and worker not in self.owners,
            "FIFO or worker identity",
        )
        valid = (
            sl["slot_gen"][slot] == key[4]
            and sl["slot_expert"][slot] == key[2]
            and sl["slot_state"][slot] == 1
            and not sl["slot_claimed"][slot]
        )
        need(valid == (kind == "DEQUEUE"), "stale classification")
        if valid:
            sl["slot_claimed"][slot] = 1
            self.owners[worker] = key

    def close(self, final):
        need(
            not self.route and not self.events and not self.waiting and not self.started,
            "unfinished controller",
        )
        need(
            not self.queue
            and not self.owners
            and not final["queue"]
            and not any(w["phase"] for w in final["owned"]),
            "undrained replay cut",
        )
        for field in ("n_calls", "hot_decay_interval", "next_work_id"):
            need(self.s[field] == final[field], f"final manager {field}")
        for sl, actual in zip(self.s["layers"], final["layers"], strict=True):
            for field in (
                *VECTORS,
                "use_counter",
                "n_slots",
                "plan_capacity",
                "n_waves",
                "next_wave",
            ):
                need(sl[field] == actual[field], f"final layer {sl['layer']} {field}")


def replay(initial, final, rows, routing):
    known = [r for r in routing if r["call_id"] in (9, 10)]
    # Last FFN is output-pruned on non-final tiles.
    short = [(9, layer, 0, 1 if layer == 35 else 5) for layer in range(36)]
    long = [(10, layer, 1, w) for w in (32, 32, 32, 32, 20) for layer in range(35)]
    expected = short + long + [(10, 35, 0, 1)]
    need(
        [(r["call_id"], r["layer"], r["mode"], len(r["ids"]) // 4) for r in known] == expected,
        "prefill routed geometry",
    )
    routes = {r["transition_seq"]: r for r in known}
    need(len(routes) == len(known), "two route starts share a journal marker")
    c = Controller(initial)
    for event in rows:
        if not initial["transition_seq"] <= event["seq"] < final["transition_seq"]:
            continue
        if event["seq"] in routes:
            c.begin_route(routes.pop(event["seq"]))
        c.consume(event)
    need(not routes, "missing route start")
    c.close(final)
    return {
        "status": "PREFILL_LOGICAL_REPLAY_MATCHED",
        "events": dict(c.count),
        "manager_route_calls": final["n_calls"] - initial["n_calls"],
        "equal_layer_fields": list(VECTORS)
        + ["use_counter", "n_slots", "plan_capacity", "n_waves", "next_wave"],
        "reconciled_layers": len(final["layers"]),
        "pending_work_at_both_cuts": 0,
    }
