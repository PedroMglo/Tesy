"""Recover ordered OFF matrix requests and size a bounded pageable staging ablation."""

import argparse
import hashlib
import json
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
A = run_path(str(HERE / "real_authority.py"))
T = A["OFF"]["T"]
need = A["need"]
PAGE = 4096


def counters(lines, plan, slots, ledger):
    need(T["compare"](lines, plan, slots, ledger)["match"], "unproved OFF file and slot transfers")
    starts = sorted(
        (off, off + n, int(m[1]), m[2])
        for name, (off, n, _) in plan.items()
        if (m := T["FILE_NAME"].fullmatch(name))
    )
    ids = [s[0] for s in starts]
    schedule = []
    for line in lines:
        f = line.split()
        if (
            len(f) < 2
            or f[0] != "SET"
            or f[1] not in ("3", "4")
            or not T["BANK_NAME"].fullmatch(f[5])
        ):
            continue
        phase, at, n, offset = map(int, (f[1], f[7], f[8], f[10]))
        i = bisect_right(ids, offset) - 1
        start, stop, layer, role = starts[i]
        need(i >= 0 and start <= offset < offset + n <= stop, "source range")
        schedule.append((phase, layer, role, offset, at, n))
    site_order = [(phase, layer) for phase, layer, *_ in schedule]
    need(site_order == sorted(site_order), "layer order")
    result = {}
    for phase, name in ((3, "prefill"), (4, "teacher")):
        rows = [r for r in schedule if r[0] == phase]
        live = defaultdict(int)
        max_payload = max_aligned = 0
        for _, layer, _, fo, _, n in rows:
            # Keep the source pointer's offset within its page. Reuse is allowed
            # only after every CUDA consumer of that region has drained.
            alloc = (n + fo % PAGE + PAGE - 1) // PAGE * PAGE
            live[layer] += alloc
            max_payload = max(max_payload, n)
            max_aligned = max(max_aligned, alloc)
        result[name] = dict(
            sets=len(rows),
            active_layers=len(live),
            payload_B=sum(r[-1] for r in rows),
            one_set_max_payload_B=max_payload,
            one_set_max_scratch_B=max_aligned,
            one_layer_max_scratch_B=max(live.values()),
            two_alternating_fixed_buffers_B=2 * max(live.values()),
            layer_fences_for_serial_layer_fixture=len(live),
        )
    return dict(
        ordered_sha256=hashlib.sha256(
            json.dumps(schedule, separators=(",", ":")).encode()
        ).hexdigest(),
        first_layer=schedule[0][1],
        last_layer=schedule[-1][1],
        phases=result,
    )


def run(a):
    p = A["receipt"](a.family / "receipt.json", a.family_sha256)
    need(
        p["status"] == "PASS_CALLBACK_OFF_TWO_CUTS"
        and p["model_starts"] == 4
        and A["sha"](a.plan) == A["PLAN"],
        "physical pair",
    )
    result = {}
    for mode in ("BANK288", "BANK161"):
        on = a.family / "ON" / mode
        off = a.family / "OFF" / mode
        for label, path in (("ON", on), ("OFF", off)):
            receipt = A["receipt"](
                path / "receipt.json", p["arms"][label + "/" + mode]["receipt_sha256"]
            )
            need(A["FR"]["inventory"](path) == receipt["raw_sha256"], "arm inventory")
        g = A["G"]["check_arm"](
            mode,
            (on / "raw/stdout").read_text(),
            (on / "raw/stderr").read_text(),
            on / "native",
            a.plan,
        )
        need(
            A["OFF"]["grade"](mode, off, a.plan, a.family / "ON", g)["status"]
            == "PASS_CALLBACK_OFF_TWO_CUTS",
            "same service",
        )
        result[mode] = counters(
            (off / "raw/stdout").read_text().splitlines(),
            A["G"]["CAP"]["tensor_plan"](a.plan),
            g["slots"],
            g["ledger"],
        )
    return dict(
        status="TRACE_DERIVED_STAGING_CAPACITY",
        family_sha256=a.family_sha256,
        page_B=PAGE,
        arms=result,
        model_starts=0,
        measured_staging_s=None,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family", type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a)
    except Exception as exc:
        result = dict(status="FAIL_PRESERVED", reason=str(exc))
    (a.new_output_dir / "review.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n"
    )
    print(result["status"], result.get("reason", ""))
    raise SystemExit(result["status"] == "FAIL_PRESERVED")
