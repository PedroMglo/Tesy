"""Inspect native C317 speculative FIFO eligibility at a pinned blocking attach."""

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from audit import WORKERS, audit, primary, require, source, staging  # noqa: E402


class StageQueue:
    """S1..S8 under the C305 mutex. Expired in-flight reads still occupy the pool."""

    def __init__(self):
        self.queued = set()
        self.running = set()
        self.pure = set()

    def next_ticket(self):
        return min(self.queued) if self.queued and len(self.pure) < 3 else None

    def event(self, ticket, kind):
        if kind == 1:
            self.queued.add(ticket)
        elif kind == 2:
            require(self.next_ticket() == ticket, "stage dispatch violates priority or capacity")
            self.queued.remove(ticket)
            self.running.add(ticket)
            self.pure.add(ticket)
        elif kind == 3:
            self.running.remove(ticket)
            self.pure.discard(ticket)
        elif kind == 4:
            self.queued.discard(ticket)
        elif kind == 6:
            self.pure.discard(ticket)
            return ticket in self.running
        return False


def terminal(positions):
    if 2 not in positions:
        return "removed_queued"
    if 6 in positions:
        return "consumed_from_reading" if positions[6][0] < positions[3][0] else "consumed_ready"
    return "expired_running" if 5 in positions else "expired_ready"


def inspect_arm(text, data):
    locked = audit(text, data)
    require(locked["ambiguous_occupancy_at_accepts"] == 0, "unresolved locked staging prefix")
    events, _, _, _, primary_depth, pending, _ = primary(text)
    p5 = {e.work: i for i, e in enumerate(events, 1) if e.kind == 5}
    tickets, stage_depth, _, stats = staging(data)
    pos = {t: {e["kind"]: (i, e) for i, e in seq} for t, seq in tickets.items()}
    shadow = StageQueue()
    partition, class_counts, outcomes, target_offsets = Counter(), Counter(), Counter(), Counter()
    unique_heads = set()
    never_started_nonheads = set()
    attachments = 0
    witness = None
    first_reading_attach = None
    for j, event in enumerate(data["journal"], 1):
        ticket = (event["scope"], event["ticket"])
        if not shadow.event(ticket, event["kind"]):
            continue
        attachments += 1
        claim = pos[ticket][7][1]
        work = tuple(claim[f] for f in ("call", "layer", "expert", "slot", "generation"))
        p = p5[work]
        require(len(shadow.running) == stage_depth[j - 1], "producer count at locked attach")
        heads = pending[p]
        assigned = primary_depth[p] + len(shadow.running)
        eligible = shadow.next_ticket()
        bucket = "primary_pending" if heads else "primary_empty"
        avail = "stage_eligible" if eligible else "stage_ineligible"
        partition[bucket + "/" + avail] += 1
        if first_reading_attach is None:
            first_reading_attach = [p, j]
        if heads or eligible is None:
            continue
        class_counts["full" if assigned == WORKERS else "spare"] += 1
        if assigned != WORKERS:
            continue
        future = pos[eligible]
        proposed = future[1][1]
        require(proposed["call"] == event["call"], "future ticket crosses a call")
        delta = proposed["layer"] - event["layer"]
        require(0 < delta <= 2, "eligible ticket outside the two-layer prediction horizon")
        target_offsets[delta] += 1
        fate = terminal(future)
        outcomes[fate] += 1
        unique_heads.add(eligible)
        never_started_nonheads.update(t for t in shadow.queued if t != eligible and 2 not in pos[t])
        if witness is None:
            witness = {
                "primary_P5_decode_index": p,
                "stage_S6_index": j,
                "also_first_reading_attach_in_blocking_arm": first_reading_attach == [p, j],
                "blocked": dict(
                    zip(("call", "layer", "expert", "slot", "generation"), work, strict=True)
                ),
                "primary_pending_after_accept": heads,
                "assigned_primary_including_waiter": primary_depth[p],
                "assigned_producers": len(shadow.running),
                "speculative_after_attach": len(shadow.pure),
                "stage_tickets_queued": len(shadow.queued),
                "fifo_head": {
                    k: proposed[k] for k in ("scope", "ticket", "call", "layer", "expert")
                },
                "head_staging_cycle_in_control": [e["kind"] for _, e in tickets[eligible]],
                "head_observed_S2_index": future[2][0] if 2 in future else None,
                "head_control_outcome": fate,
            }
    require(not (shadow.queued or shadow.running or shadow.pure), "unfinished shadow")
    require(attachments == stats["waits"] == sum(partition.values()), "attachment conservation")
    require(
        sum(n for k, n in partition.items() if k.startswith("primary_pending/"))
        == locked["other_work_at_blocked_accept"]["pending_accepted_later"],
        "primary backlog differs from locked auditor",
    )
    return {
        "reading_attach_observations": attachments,
        "after_attach_observations": dict(sorted(partition.items())),
        "stage_dispatch_eligible_without_primary_by_occupancy": dict(sorted(class_counts.items())),
        "full_pool_empty_primary_eligible_stage": {
            "observations": sum(outcomes.values()),
            "distinct_head_tickets_within_arm": len(unique_heads),
            "target_layer_minus_blocked_layer": dict(sorted(target_offsets.items())),
            "observed_head_terminal_by_episode": dict(sorted(outcomes.items())),
            "distinct_nonhead_tickets_seen_queued_but_never_started_in_control": len(
                never_started_nonheads
            ),
            "first_witness_in_blocking_arm": witness,
        },
    }


def run(raw_root, out):
    out.mkdir()
    manifest = source.required_files()
    receipt = {
        "schema": "tesy-c317-post-attach-speculative-head-v1",
        "evidence": "TRACE_DERIVED_RETROSPECTIVE",
        "pin": "c94780b12820c7b3fb20f2a9acf38bb27506c6ae",
        "inputs": manifest,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "condition": "One isolated detach after the identical blocking prefix under the mutex.",
        "end_to_end_byte_or_latency_difference": "INCONCLUSIVE",
        "arms": {},
    }
    try:
        missing = sorted(f for f in manifest if not (raw_root / f).is_file())
        if missing:
            receipt.update(status="NOT_RUN_RAW_REQUIRED", missing=missing)
            return 2
        # All eight immutable originals are admitted before either journal is interpreted.
        raw = {f: source.checked_bytes(raw_root / f, pin) for f, pin in manifest.items()}
        for f, payload in raw.items():
            if f.endswith("/events.tsv"):
                arm = f.removesuffix("/events.tsv")
                receipt["arms"][arm] = inspect_arm(
                    payload.decode(), json.loads(raw[arm + "/staging.json"])
                )
        require(len(receipt["arms"]) == 4, "expected four trace-ON controls")
        receipt["status"] = "PASS_BLOCKING_PREFIX_CLASSIFICATION"
        return 0
    except (OSError, ValueError, KeyError) as err:
        receipt.update(status="FAIL", reason=str(err))
        return 1
    finally:
        part = out / "fila.json.part"
        with part.open("x", encoding="utf-8") as handle:
            json.dump(receipt, handle, indent=2, allow_nan=False, sort_keys=True)
            handle.write("\n")
        part.rename(out / "fila.json")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--raw-dir", required=True, type=Path)
    cli.add_argument("--new-output-dir", required=True, type=Path)
    opts = cli.parse_args()
    raise SystemExit(run(opts.raw_dir, opts.new_output_dir))
