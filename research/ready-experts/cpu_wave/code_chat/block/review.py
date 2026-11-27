"""Reopen numerical captures and independently compare both genuine cuts across four processes."""

import argparse
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
B = run_path(HERE / "run.py")
need, sha, read, save = (B[k] for k in ("need", "sha", "read", "save"))


def review(folder, h):
    r = B["checked"](folder / "receipt.json", h)
    need(
        r["status"] == "PASS_TWO_CODE_CUTS" and [a["role"] for a in r["arms"]] == list(B["ORDER"]),
        "complete family",
    )
    proofs = {}
    arms = []
    for arm in r["arms"]:
        role = arm["role"]
        src = folder / role
        raw = src / "raw"
        unit = arm["unit"]
        cap = raw / (unit + ".capture")
        m = B["checked"](raw / (unit + ".json"), arm["monitor_sha256"])
        inv = B["checked"](src / "invocation.json", arm["argv_sha256"])
        cfg = B["checked"](src / "resource.json", m["limits"]["resource_protocol_sha256"])
        launch = read(raw / (unit + ".launch.json"))
        need(
            m["returncode"] == 0
            and m["stop_reason"] is None
            and m["mapped_libraries_match_ldd"]
            and m["process_identity"] == launch["process_identity"]
            and m["command"] == inv["command"][-5:]
            and m["explicit_env"] == inv["expected"]
            and cfg["pinned"]["capture_sha256"] == m["binary_sha256"]
            and cfg["pinned"]["ids_sha256"] == m["workload_sha256"]
            and cfg["measurement_commit"] == r["commit"]
            and m["maxima"] == arm["maxima"]
            and m["cgroup_end"]["memory_max"] == 20 << 30
            and m["cgroup_end"]["swap_max"] == m["maxima"]["swap_bytes"] == 0,
            "resource and process authority",
        )
        need(
            all(
                sha(raw / (unit + suffix)) == digest
                for suffix, digest in m["output_sha256"].items()
            ),
            "native output seals",
        )
        proof = B["GRADE"]["inspect"](cap, role)
        need(proof == B["checked"](src / "proof.json", arm["proof_sha256"]), "raw numerical proof")
        proofs[role] = proof
        observed = B["GRADE"]["compare"](proofs, role)
        need(
            observed == read(src / "comparison.json")
            and all(observed.values())
            and len(observed) == arm["comparisons"],
            "numerical comparison",
        )
        cuts = []
        for at in (1, 9):
            decision = read(cap / f"{at}-decision.json")
            cuts.append(
                dict(
                    confirmed_before=at,
                    position=2104 + at,
                    scheduled=decision["scheduled"],
                    accepted=decision["accepted"],
                    logits_sha256=[
                        proof["values"][f"{at}-row-{i}.f32"] for i in range(decision["scheduled"])
                    ],
                    kept=proof["values"][f"{at}-keep.json"],
                    store=proof["loads"].get(f"{at}-store"),
                )
            )
        need(B["POWER"](src, dict(unit=unit)) == arm["energy"], "GPU energy from telemetry")
        arms.append(
            dict(
                role=role,
                unit=unit,
                comparisons=len(observed),
                finite_rows=sum(p.endswith(".f32") for p in proof["values"]),
                cuts=cuts,
                scope_s=arm["scope_s"],
                process_s=arm["model_s"],
                c118_s=arm["c118"]["s"],
                energy=arm["energy"],
                maxima=arm["maxima"],
                pack_fd_samples=arm["pack_fd_samples"],
                graph_layers=arm["layers"],
                proof_sha256=arm["proof_sha256"],
            )
        )
    return dict(
        status="PASS_TWO_CODE_CUTS",
        decision="GO_PRICE_ONLY",
        commit=r["commit"],
        tree=r["tree"],
        family_sha256=h,
        build_sha256=r["client_sha256"],
        window_sha256=r["window_sha256"],
        protocol_sha256=r["protocol_sha256"],
        program_sha256=sha(HERE / "run.py"),
        grader_sha256=sha(HERE / "grade.py"),
        elapsed_s=r["elapsed_s"],
        arms=arms,
    )


def check(r):
    need(
        r["status"] == "PASS_TWO_CODE_CUTS"
        and r["decision"] == "GO_PRICE_ONLY"
        and len(r["arms"]) == 4,
        "public decision",
    )
    rows = r["arms"]
    need(
        [x["role"] for x in rows] == list(B["ORDER"])
        and [x["finite_rows"] for x in rows] == [11, 9, 9, 11]
        and all(x["c118_s"] >= 60 and x["maxima"]["swap_bytes"] == 0 for x in rows),
        "arm counts",
    )
    for i in range(2):
        ref = rows[0]["cuts"][i]
        on = rows[-1]["cuts"][i]
        need(
            ref["logits_sha256"] == on["logits_sha256"]
            and all(
                x["cuts"][i]["logits_sha256"] == ref["logits_sha256"][: x["cuts"][i]["scheduled"]]
                and x["cuts"][i]["kept"] == ref["kept"]
                for x in rows
            ),
            "published distributions and cached state",
        )
    need(rows[-1]["graph_layers"] == list(range(36)), "repaired full graph")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--family", type=Path)
    cli.add_argument("--sha256")
    cli.add_argument("--check", type=Path)
    cli.add_argument("--new-output-dir", type=Path)
    a = cli.parse_args()
    if a.check:
        check(read(a.check))
    else:
        a.new_output_dir.mkdir(mode=0o700)
        try:
            result = review(a.family, a.sha256)
            check(result)
            save(a.new_output_dir / "receipt.json", result)
        except Exception as exc:
            save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
            raise
    print("PASS_TWO_CODE_CUTS")
