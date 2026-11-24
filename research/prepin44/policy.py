"""C163×44 common FIFO service rule and the current-wave pin intervention."""

from collections import Counter

from replay import Controller, need


class Fixture(Controller):
    def __init__(self, initial, mode, protect):
        super().__init__(initial)
        need(mode in ("early", "late") and initial["workers"] == 4, "service mode / worker count")
        self.mode, self.protect = mode, protect
        self.reservations = []
        self.admission_context = []
        self.tile_visits = Counter()
        self.demand_states = []
        self.evidence = Counter()

    def expect(self, kind, **fields):
        if kind == "DEMAND":
            if self.protect and self.wave >= 0 and not self.sl["demand_slots"]:
                cap = self.sl["plan_capacity"]
                current = self.sl["uniq"][self.wave * cap : (self.wave + 1) * cap]
                for expert in current:
                    slot = self.sl["expert_slot"][expert]
                    if slot >= 0 and self.sl["slot_state"][slot] == 2:
                        self.sl["keep"][slot] = 1
            self.demand_states.append(
                (self.route["call_id"], self.sl["layer"], fields["expert"], fields["state"])
            )
        if kind == "RESERVE":
            layer, call = self.sl["layer"], self.route["call_id"]
            cap, wave = self.sl["plan_capacity"], self.wave
            upcoming = self.sl["uniq"][(wave + 1) * cap : (wave + 2) * cap] if wave >= 0 else []
            service = "preload" if fields["expert"] in upcoming else "demand"
            tile = 4 if (call, layer) == (10, 35) else self.tile_visits[call, layer] - 1
            self.admission_context.append((call, tile, layer, wave, fields["expert"], service))
            self.reservations.append(
                (
                    self.route["call_id"],
                    self.sl["layer"],
                    fields["expert"],
                    fields["slot"],
                    fields["generation"],
                )
            )
        self.evidence[kind] += 1
        super().expect(kind, **fields)

    def worker_step(self, kind, key, worker):
        row = dict(
            zip(("call_id", "layer", "expert", "slot", "generation", "work_id"), key, strict=True)
        )
        row.update(kind=kind, component=worker)
        self.worker(row)
        self.evidence[kind] += 1

    def dispatch(self):
        for worker in range(4):
            while worker not in self.owners and self.queue:
                key = self.queue[0]
                _, layer, expert, slot, gen, _ = key
                sl = self.s["layers"][layer]
                valid = (
                    sl["slot_expert"][slot] == expert
                    and sl["slot_gen"][slot] == gen
                    and sl["slot_state"][slot] == 1
                    and not sl["slot_claimed"][slot]
                )
                self.worker_step("DEQUEUE" if valid else "STALE_WORK", key, worker)

    def serve(self, all_work):
        required = set() if all_work else set(self.sl["demand_slots"])
        while (
            (self.queue or self.owners)
            if all_work
            else any(self.sl["slot_state"][s] != 2 for s in required)
        ):
            self.dispatch()
            if not self.owners and all_work and not self.queue:
                break  # A remaining duplicate can drain as STALE without any owned work.
            need(self.owners, "barrier with no live producer")
            worker, key = min(
                self.owners.items(),
                key=lambda w: (w[1][1] != self.sl["layer"] or w[1][3] not in required, w[1][5]),
            )
            self.worker_step("RESIDENT_COMMIT", key, worker)

    def run(self, routes):
        for route in routes:
            self.tile_visits[route["call_id"], route["layer"]] += 1
            self.begin_route(route)
            while self.route:
                sl, w = self.sl, self.wave
                cap = sl["plan_capacity"]
                current = set(sl["uniq"][w * cap : (w + 1) * cap]) if w >= 0 else set(sl["uniq"])
                loading = {
                    (layer["layer"], e)
                    for layer in self.s["layers"]
                    for e, state in zip(layer["slot_expert"], layer["slot_state"], strict=True)
                    if state == 1
                }
                need(
                    not loading if w <= 0 else loading <= {(sl["layer"], e) for e in current},
                    "pending generation escapes current wave",
                )
                if w > 0:
                    need(
                        all(sl["expert_slot"][e] >= 0 for e in current),
                        "previous stage skipped a next-wave preload",
                    )
                    self.evidence["noninitial_waves_all_current_mapped"] += 1
                self.admissions()
                # Admission interests include every next-wave expert; validate even on
                # all-ready paths. This verifies the induction under both policies.
                if w >= 0:
                    upcoming = sl["uniq"][(w + 1) * cap : (w + 2) * cap]
                    need(all(sl["expert_slot"][e] >= 0 for e in upcoming), "skipped preload")
                self.events.clear()  # Generated controller rows are counted in expect().
                if self.waiting:
                    self.serve(all_work=self.mode == "early")
                    self.consume(dict(kind="WAIT_END", wave=w))
                kind = "REMAP_DONE" if w == -1 else "WAVE_DONE"
                self.consume(
                    dict(kind=kind, layer=sl["layer"], wave=w, n_tokens=len(route["ids"]) // 4)
                )
                if self.mode == "early":
                    self.serve(all_work=True)
        self.serve(all_work=True)  # Drain stale tickets for the idle comparison cut.
        need(self.evidence["RESIDENT_COMMIT"] == len(self.reservations), "unpublished reservation")


def counts(reservations):
    return dict(Counter("CPU" if layer < 25 else "CUDA0" for _, layer, *_ in reservations))


def demand_counts(demands):
    return dict(
        Counter(
            f"{'CPU' if layer < 25 else 'CUDA0'}_{('miss', 'pending', 'ready')[state]}"
            for _, layer, _, state in demands
        )
    )


def differences(baseline, candidate):
    def by_expert(rows):
        return Counter((call, layer, expert) for call, layer, expert, _, _ in rows)

    base, cand = by_expert(baseline), by_expert(candidate)

    def by_tier(work):
        totals = Counter()
        for (call, layer, _), multiplicity in work.items():
            totals[f"call{call}_{'CPU' if layer < 25 else 'CUDA0'}"] += multiplicity
        return dict(totals)

    return {"added": by_tier(cand - base), "saved": by_tier(base - cand)}
