"""One ideal T1 selection for the temporal and prefill-volume floors of PFJ1."""

import argparse
import collections
import hashlib
import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "warm_oracle_screen", Path(__file__).with_name("screen.py")
)
warm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(warm)

METHOD = "13626cc1b7b275304cd54fd67ed35e8c8665316efa59b5fd860f2bea41397071"
SINGLE = "87b2c4bcf96695a04e6f70adff14adf7d5ed24e7ef77e81218dafc3b3da14441"
need = warm.need


def volume_keys(rows):
    required = set()
    claimed = {}
    inherited = set()
    resident = set()
    for row in rows:
        gen = warm.analyse.identity(row)
        if row.kind == 5 and row.a in (1, 2):
            (inherited if row.a == 1 else resident).add((row.layer, row.expert))
        elif row.kind == 10 and row.call in (1, 2):
            required.add(gen)
        elif row.kind == 13 and row.call > 0:
            need(gen not in claimed, "duplicate dispatch")
            claimed[gen] = row.call
    selected = {(g[0], g[3]) for g in required if claimed.get(g) in (1, 2)} - inherited
    return selected, len(inherited), len(selected & resident)


def joint(pref, dec, volume, m, fixed, scale, threshold, caps):
    pk = {k for g in pref for k, _ in g}
    dk = {k for g in dec for k, _ in g}
    need(pk <= volume and not dk & volume and not pk & dk, "nonseparable wave classes")
    fillers = sorted(volume - pk)
    a, b = scale
    need(0 <= m <= len(volume) and a > 0 and b > 0, "domain")
    pd, ps = warm.optimum(pref)
    dd, ds = warm.optimum(dec)
    best = {}
    for i, p in enumerate(pd):
        f = max(0, m - i)
        if f > len(fillers):
            continue
        for j, d in enumerate(dd):
            k = i + j + f
            item = (p + d, f, i, j)
            if k not in best or item < best[k]:
                best[k] = item

    def at(cap):
        feasible = [(choice[0], k, choice) for k, choice in best.items() if k <= cap]
        if not feasible:
            return {"cap": cap, "volume_possible": False, "first_floor_ns": None}
        cost, k, (_, f, i, j) = min(feasible)
        selection = set(ps(i) + ds(j) + fillers[:f])
        need(len(selection) == k and len(volume & selection) >= m, "joint witness size")
        observed = sum(
            warm.lower_bound([v for key, v in g if key not in selection]) for g in [*pref, *dec]
        )
        need(observed == cost, "joint witness service")
        return dict(
            cap=cap,
            volume_possible=True,
            used=k,
            temporal_prefill=i,
            temporal_decode=j,
            fillers=f,
            selected_useful_prefill=len(selection & volume),
            first_floor_ns=fixed + a * cost // b,
            prefill_volume_floor_bytes=(len(volume) - len(selection & volume)) * warm.PAYLOAD,
            prepared_payload_bytes=k * warm.PAYLOAD,
            selected_keys_sha256=hashlib.sha256(
                json.dumps(sorted(selection), separators=(",", ":")).encode()
            ).hexdigest(),
        )

    feasible = [k for k, (cost, _, _, _) in best.items() if fixed + a * cost // b <= threshold]
    k = min(feasible) if feasible else None
    return {
        "minimum": at(k) if k is not None else None,
        "one_fewer": at(k - 1) if k else None,
        "capacity": [at(n) for n in caps],
    }


def run(plan_dir, on_dir):
    single = warm.read(warm.HERE / "receipt.json", SINGLE)
    pins = single["source"]
    need(
        warm.sha(warm.HERE / "joint-protocol.md") == METHOD
        and warm.sha(warm.HERE / "screen.py") == pins["code"]
        and warm.sha(warm.INT / "mandatory.py") == pins["mandatory"]
        and warm.sha(Path(warm.analyse.__file__)) == pins["analyser"],
        "implementation pins",
    )
    meta = warm.read(plan_dir / "receipt.json", pins["plan_receipt"])
    plan = warm.read(plan_dir / "plan.json", pins["plan"])
    rows, header = warm.analyse.read_journal(on_dir / "raw/events.pfj")
    need(header["journal_sha256"] == pins["journal"], "journal seal")
    clocks = warm.read(on_dir / "raw/T2-result.json", meta["t2_result_sha256"])
    start = int(clocks["request_started_monotonic"] * 10**9)
    first = start + int(clocks["stream_metrics"]["first_final_content_chunk_s"] * 10**9)
    spans = collections.defaultdict(dict)
    for r in rows:
        if r.kind in (9, 23):
            site = (r.call, r.tile, r.layer, r.wave)
            need(r.kind not in spans[site], "duplicate callback boundary")
            spans[site][r.kind] = r.ns
    groups = warm.jobs(plan, rows)
    pre = []
    dec = []
    for g, definition in zip(groups, plan["groups"], strict=True):
        site = tuple(definition["site"])
        span = spans[site]
        need(
            start + 10**6 <= span[9] < span[23] <= first - 10**6,
            "time-eligible before client cutoff",
        )
        (pre if site[0] <= 2 else dec).append(g)
    # The authenticated independent plan already proved that each job's three reads
    # are inside its own callback; a final digest prevents substituting another plan.
    need(
        meta["plan_sha256"] == pins["plan"] and meta["journal_sha256"] == pins["journal"],
        "plan/job scope",
    )
    volume, inherited, resident = volume_keys(rows)
    host = warm.read(warm.INT / "host_cache/evidence/receipt.json", pins["host_cache"])
    need(
        len(volume) == host["required_distinct"]
        and inherited == host["inherited_keys_granted_free"]
        and resident == host["initial_resident_reloads"]
        and (sum(layer < 25 for layer, _ in volume), sum(layer >= 25 for layer, _ in volume))
        == (host["required_by_tier"]["cpu"], host["required_by_tier"]["cuda"]),
        "volume identity reconciliation",
    )
    pkeys = {key for g in pre for key, _ in g}
    dkeys = {key for g in dec for key, _ in g}
    need(
        len(pkeys) + len(dkeys) == single["unique_keys"]
        and len(pkeys) == sum(map(len, pre))
        and len(dkeys) == sum(map(len, dec)),
        "unique temporal keys",
    )
    result = {}
    for label, goal in single["volume"].items():
        result[label] = {}
        for a, b in ((1, 1), (4, 5)):
            ans = joint(
                pre,
                dec,
                volume,
                goal["minimum"],
                single["first_fixed_ns"],
                (a, b),
                10**10,
                warm.CAPS,
            )
            for z in [ans["minimum"], *ans["capacity"]]:
                if z and z["volume_possible"]:
                    need(z["prefill_volume_floor_bytes"] <= goal["allowed_bytes"], "volume witness")
            result[label][f"{a}/{b}"] = ans
    return {
        "status": "PASS_SAME_INITIAL_SELECTION_FOR_TWO_FLOORS",
        "joint": result,
        "membership": {
            "volume_keys": len(volume),
            "time_keys": len(pkeys | dkeys),
            "time_prefill": len(pkeys),
            "time_decode": len(dkeys),
            "volume_and_time_prefill": len(volume & pkeys),
            "volume_and_time_decode": len(volume & dkeys),
            "volume_only": len(volume - (pkeys | dkeys)),
        },
        "source": dict(
            pins,
            joint_code=warm.sha(Path(__file__)),
            joint_protocol=METHOD,
            single_receipt=SINGLE,
            t2_client_sha256=meta["t2_result_sha256"],
        ),
        "causal_preparation": "NOT_DEMONSTRATED",
        "attainable_service_schedule": "NOT_DEMONSTRATED",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for opt in ("plan-dir", "on-dir", "new-output-dir"):
        p.add_argument("--" + opt, required=True, type=Path)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        ans = run(a.plan_dir, a.on_dir)
    except (ValueError, KeyError, IndexError, TypeError, OSError) as exc:
        ans = {"status": "FAIL_PRESERVED", "type": type(exc).__name__, "reason": str(exc)}
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(ans, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    print(ans["status"])
    raise SystemExit(ans["status"] == "FAIL_PRESERVED")
