"""Reconcile the actual prompts, streams, telemetry and lookup schedule of the HTTP family."""

import argparse
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
F = run_path(HERE / "family.py")
H, S, T, need, sha, read, publish = (
    F[k] for k in ("H", "S", "T", "need", "sha", "read", "publish")
)
LOOK = run_path(HERE.parent / "lookup.py")
PRIOR = run_path(HERE.parent / "review.py")


def reopen(a):
    r = H["G"]["read"](a.family / "receipt.json", a.sha256)
    need(
        r["status"] == "COMPLETE_CODE_PRICE"
        and tuple(r["order"]) == F["ORDER"]
        and r["cut_sha256"] == F["NUMERIC"],
        "sealed price family",
    )
    source = read(a.family / "provenance.json")
    need(
        source["program_sha256"] == sha(HERE / "family.py")
        and source["trajectory_sha256"] == sha(HERE / "trajectory.py")
        and r["protocol_sha256"] == sha(HERE / "protocol.md"),
        "frozen method",
    )
    receipt = H["G"]["read"](a.build / "receipt.json", F["CUT"]["CLIENT"])
    w = H["G"]["read"](a.build / "work.json", receipt["files"]["work.json"])
    inputs = {
        "T1": dict(prompt=w["t1"], target=w["first"], cap=256),
        "T2": dict(prompt=w["t2"], target=w["target"], cap=768),
    }
    original = a.archive / "part-177/tesy-packed-causal-plan-20261126-r03"
    orig = H["G"]["read"](original / "receipt.json", H["PLAN_PIN"])
    steps = {
        "T1": H["G"]["read"](original / "r0.stdout", orig["same_output_sha256"])["T1"],
        "T2": H["G"]["read"](
            a.replay / "steps.json", read(HERE.parent / "lookup.json")["steps_sha256"]
        )["T2"],
    }
    out = []
    for i, arm in enumerate(r["arms"], 1):
        name, role, unit = arm["folder"], arm["role"], arm["unit"]
        need(name == str(i) + role and F["ORDER"][i - 1] == role, "role and sequence")
        root = a.family / name
        raw = root / "raw"
        row = H["G"]["read"](root / "receipt.json", arm["receipt_sha256"])
        need(
            row["status"] == "MEASURED"
            and row["trial"]
            == {k: v for k, v in arm.items() if k not in ("folder", "receipt_sha256")},
            "per-process receipt",
        )
        ses = H["G"]["read"](root / "session.json", arm["session_sha256"])
        mon = H["G"]["read"](raw / (unit + ".json"), ses["monitor_sha256"])
        need(
            all(sha(raw / (unit + k)) == v for k, v in mon["output_sha256"].items())
            and mon["returncode"] == 0
            and mon["stop_reason"] == "INTERRUPTED_BY_OWNER"
            and mon["mapped_libraries_match_ldd"]
            and mon["cgroup_end"]["memory_max"] == 20 << 30
            and mon["cgroup_end"]["swap_max"] == mon["maxima"]["swap_bytes"] == 0
            and row["cleanup"]
            == ses["cleanup"]
            == "SERVER_EXIT_0_OWNER_STOP_UNIT_CLOSED_PORT_AVAILABLE",
            "authentic termination",
        )
        opts = read(root / "arm-inputs.json")
        need(
            opts["env"].get("TESY_NATIVE_CPU_WAVE") == "1"
            and ("--spec-type" in opts["argv"]) == (role == "ON")
            and ("TESY_B3_CPU_LONG_ROWS" in opts["env"]) == (role == "ON")
            and opts["numerical_gate"] == F["NUMERIC"],
            "live intervention",
        )
        log = (raw / (unit + ".stderr")).read_bytes()
        for j, t in enumerate(arm["turns"], 1):
            k = f"T{j}"
            result = read(raw / (k + "-result.json"))
            need(
                t == PRIOR["READER"](result, raw, j, ids_hash=H["SESSION"].ids_hash)
                and result["accepted"]
                and read(raw / (k + "-functional.json"))["status"] == "PASS"
                and result["official_ids"] == inputs[k]["prompt"]
                and (t["prompt"], t["cached"], t["evaluated"])
                == ((2043, 0, 2043) if j == 1 else (2105, 2044, 61)),
                "native input and user-visible clocks",
            )
            grade = F["TRAJ"]["evaluate"](log, j, inputs[k], steps[k], role == "ON", H["T"])
            need(
                arm["ids"][str(j)] == grade and t["predicted"] == t["output"] == grade["sampled"],
                "confirmed tokens",
            )
        need(
            S["grader"].grade(S["W"]["GRADER"], result["message"]["content"])["status"] == "PASS",
            "RLE function",
        )
        inv = S["PK"]["PK"]["compact"].validate_inventory(
            root, unit, dict(native_explicit_env=opts["env"]), read(raw / (unit + ".launch.json"))
        )
        need(
            inv["s"] == arm["c118_s"] and arm["energy"] == PRIOR["POWER"](root, arm),
            "C118 or power",
        )
        native = arm["ids"]["2"]
        t2 = arm["turns"][1]
        decode_ns = round(t2["decode_s"] * 1e9)
        price = dict(
            ordinary_ns=native["ordinary_ns"],
            block_ns=native["block_ns"],
            blocks=native["blocks"],
            accepted=native["accepted"],
            native_span_ns=native["sample_span_ns"],
            server_decode_ns=decode_ns,
            residual_ns=decode_ns - native["sample_span_ns"],
        )
        if role == "ON":
            price["observed_mean_block_ns"] = native["block_ns"] // native["blocks"]
        else:
            trial = dict(unit=unit, target_ids=arm["ids"])
            entry, ticks, cut, _ = LOOK["evidence"](root, trial)
            need(entry == inputs["T2"], "serial evidence")
            price["conditional"] = LOOK["budget"](steps["T2"], ticks, cut, decode_ns)
        proof = row["runtime_authority"]
        cleanup = (proof["verified_cleanup_ns"] - proof["cuts"][-1]["monotonic_ns"]) / 1e9
        out.append(
            dict(
                role=role,
                folder=name,
                unit=unit,
                turns=arm["turns"],
                price=price,
                trajectories=arm["ids"],
                cleanup_after_last_cut_s=cleanup,
                c118_s=arm["c118_s"],
                maxima=arm["maxima"],
                energy=arm["energy"],
                model_s=arm["model_s"],
                receipt_sha256=arm["receipt_sha256"],
            )
        )
    verdict, pairs = F["decision"](out)
    need(verdict == r["decision"] and pairs == r["pairs"], "blinded pair decision")
    return dict(
        status="MEASURED_CODE_PRICE",
        decision=verdict,
        pairs=pairs,
        arms=out,
        commit=r["commit"],
        tree=r["tree"],
        family_sha256=a.sha256,
        cut_sha256=r["cut_sha256"],
        window_sha256=r["window_sha256"],
        elapsed_s=r["elapsed_s"],
        protocol_sha256=r["protocol_sha256"],
    )


def compact(r):
    need(
        r["status"] == "MEASURED_CODE_PRICE"
        and tuple(v["role"] for v in r["arms"]) == F["ORDER"]
        and r["cut_sha256"] == F["NUMERIC"],
        "public family",
    )
    verdict, pairs = F["decision"](r["arms"])
    need(r["decision"] == verdict and r["pairs"] == pairs, "public pairs")
    for arm in r["arms"]:
        enabled = arm["role"] == "ON"
        p = arm["price"]
        n = arm["trajectories"]["2"]
        turn = arm["turns"][1]
        need(
            (p["blocks"], p["accepted"], n["serial"]) == ((46, 40, 169) if enabled else (0, 0, 255))
            and n["sampled"] == turn["output"] == 256
            and n["sampled_sha256"]
            == "ab91194494825c85b4f825253e55c980837129c6fc1159ab750ac2a8144eaf27"
            and turn["validator"] == "PASS"
            and turn["stop"] == "stop"
            and turn["first_final_s"] <= turn["valid_s"]
            and p["ordinary_ns"] + p["block_ns"]
            == p["native_span_ns"]
            == p["server_decode_ns"] - p["residual_ns"]
            and arm["maxima"]["swap_bytes"] == 0
            and arm["c118_s"] >= 60,
            "published ledger",
        )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for arg in ("family", "build", "archive", "replay", "new-output-dir", "check"):
        cli.add_argument("--" + arg, type=Path)
    cli.add_argument("--sha256")
    a = cli.parse_args()
    if a.check:
        compact(read(a.check))
    else:
        a.new_output_dir.mkdir(mode=0o700)
        try:
            r = reopen(a)
            compact(r)
            publish(a.new_output_dir / "receipt.json", r)
        except Exception as exc:
            publish(
                a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc))
            )
            raise
    print("PASS_CODE_PRICE_REVIEW")
