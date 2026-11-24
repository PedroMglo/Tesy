"""Matched model-free policy tests on the two preregistered C163 nominal arms."""

import argparse
import hashlib
import json
import os
import sys
from copy import deepcopy
from pathlib import Path

BASELINE_SHA = "b3dd3e6796a41c93f39e580f8c34af8228db6c665347ec56e5b3d43f91c3156b"
INPUT_SHAS = {
    "6cc2fc0594bfff876a63f7ebd3bd89a43185644445dd292fb04fcfa9e5e25aa4",
    "cfea049ef5b61c1b9ac73495a219db9d7e9e581a32cd030cd6f00bd7ad976949",
}
PROTOCOL_SHA = "2a70e442ecc5d830f35decde6e58c34d682580907961e355df47031880b0abed"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signature(records):
    return hashlib.sha256(json.dumps(records, separators=(",", ":")).encode()).hexdigest()


def arm_report(raw, ledger, arm, control_only):
    from c152_snapshot_read import VECTORS
    from policy import Fixture, counts, demand_counts, differences
    from replay import need, replay
    from study import inputs

    initial, final, journal, routes, _ = inputs(raw, ledger, arm)
    historic = replay(initial, final, journal, routes)
    need(historic["status"] == "PREFILL_LOGICAL_REPLAY_MATCHED", "journal reproduction failed")
    prefill = [r for r in routes if r["call_id"] in (9, 10)]
    decode = [r for r in routes if r["call_id"] == 11]
    need(
        len(decode) == 36 and all(r["mode"] == 0 and len(r["ids"]) == 4 for r in decode),
        "first decode route shape",
    )
    controls = {}
    history = {}
    for calls in ((9, 10), (11,)):
        history[calls] = [
            tuple(r[k] for k in ("call_id", "layer", "expert", "slot", "generation"))
            for r in journal
            if r["call_id"] in calls and r["kind"] == "RESERVE"
        ]
    result = {"historical_control": historic["status"], "schedules": {}}
    fields = (*VECTORS, "use_counter", "plan_capacity", "next_wave", "n_waves")
    for mode in ("early", "late"):
        control = Fixture(initial, mode, False)
        control.run(prefill)
        need(
            control.reservations == history[9, 10]
            and all(
                sl[f] == other[f]
                for sl, other in zip(control.s["layers"], final["layers"], strict=True)
                for f in fields
            ),
            "control differs from historical payload / policy",
        )
        snap = deepcopy(control.s)
        cut, demands = len(control.reservations), len(control.demand_states)
        work = dict(control.evidence)
        control.run(decode)
        need(control.reservations[cut:] == history[11,], "first decode control")
        controls[mode] = (control, snap, cut, demands)
        result["schedules"][mode] = {
            "control": {
                "prefill_reserve": counts(control.reservations[:cut]),
                "prefill_events": work,
                "first_decode": demand_counts(control.demand_states[demands:]),
                "same_journaled_reservations": True,
                "equal_prefill_layer_state": True,
            }
        }
    if control_only:
        return result

    from restore import restore_layers

    for mode in ("early", "late"):
        control, target, cut, _ = controls[mode]
        cand = Fixture(initial, mode, True)
        cand.run(prefill)
        n, m = len(cand.reservations), len(cand.demand_states)
        restoration = restore_layers(cand.s["layers"], target["layers"])
        work = dict(cand.evidence)
        relative_id = cand.s["next_work_id"] - target["next_work_id"]
        need(cand.s["n_calls"] == target["n_calls"], "route clock changed")
        need(not cand.queue and not cand.owners, "restoration would discard live work")
        # restore_layers has separately executed both charged symbolic payload plans.
        # At this drained cut apply the metadata of the matched R0 shadow, including
        # its work-token namespace. This operation still needs a priced runtime.
        restored_cut = deepcopy(cand.s)
        for sl, reference in zip(restored_cut["layers"], target["layers"], strict=True):
            for field in fields:
                if sl[field] != reference[field]:
                    sl[field] = deepcopy(reference[field])
        restored_cut["next_work_id"] = target["next_work_id"]
        need(restored_cut == target, "unreconciled manager or layer metadata")
        restored = Fixture(restored_cut, mode, True)
        restored.run(decode)
        need(
            restored.s["layers"] == control.s["layers"]
            and restored.reservations == control.reservations[cut:]
            and restored.s["next_work_id"] == control.s["next_work_id"],
            "restoring reference metadata failed first decode",
        )
        cand.run(decode)
        result["schedules"][mode]["candidate"] = {
            "prefill_reserve": counts(cand.reservations[:n]),
            "prefill_events": work,
            "prefill_reservation_sha256": signature(cand.reservations[:n]),
            "prefill_differences": differences(control.reservations[:cut], cand.reservations[:n]),
            "natural_first_decode": demand_counts(cand.demand_states[m:]),
            "natural_first_decode_reserve": counts(cand.reservations[n:]),
            "natural_first_decode_differences": differences(
                control.reservations[cut:], cand.reservations[n:]
            ),
            "restored_first_decode": demand_counts(restored.demand_states),
            "restored_first_decode_state_matches_control": True,
            "net_gguf_loads_saved_after_restore": {
                strategy: {
                    tier: counts(control.reservations[:cut])[tier]
                    - counts(cand.reservations[:n])[tier]
                    - value[strategy]["gguf_loads"]
                    for tier, value in restoration.items()
                }
                for strategy in ("no_scratch", "local_scratch")
            },
            "next_work_id_delta_at_cut": relative_id,
            "payload_and_metadata_restoration": restoration,
        }
    need(
        result["schedules"]["early"]["candidate"]["prefill_reservation_sha256"]
        == result["schedules"]["late"]["candidate"]["prefill_reservation_sha256"],
        "schedule-dependent physical admissions",
    )
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--replay-dir", type=Path, required=True)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--raw-dir", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    p.add_argument("--control-only", action="store_true")
    a = p.parse_args()
    a.new_output_dir.mkdir()
    try:
        if (
            sha(a.replay_dir / "replay.py") != BASELINE_SHA
            or sha(a.replay_dir / "study.py") not in INPUT_SHAS
            or sha(Path(__file__).with_name("protocol.md")) != PROTOCOL_SHA
        ):
            raise ValueError("unrecognized baseline or protocol")
        sys.path[:0] = [str(a.replay_dir), str(a.repo / "tools")]
        ledger = a.repo / "results" / "c163-instrumentation-overhead-20260930T1145Z"
        outcome = {
            "schema": "tesy-prepin-c163-v1",
            "protocol_sha256": PROTOCOL_SHA,
            "baseline_controller_sha256": sha(a.replay_dir / "replay.py"),
            "baseline_reader_sha256": sha(a.replay_dir / "study.py"),
            "arms": {
                arm: arm_report(a.raw_dir, ledger, arm, a.control_only)
                for arm in ("c163-on-1", "c163-on-2")
            },
        }
        pending = a.new_output_dir / ".pending"
        with pending.open("x") as f:
            json.dump(outcome, f, indent=2, allow_nan=False)
            f.write("\n")
        os.replace(pending, a.new_output_dir / "receipt.json")
    except Exception as exc:
        with (a.new_output_dir / "FAIL.json").open("x") as f:
            json.dump({"exception": type(exc).__name__, "reason": str(exc)}, f)
        raise


if __name__ == "__main__":
    main()
