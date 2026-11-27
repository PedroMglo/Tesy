"""Reopen the six physical arms, independently grade the code and seal the client clocks."""

import argparse
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
S = run_path(HERE / "run.py")
H, W, need, sha, read = (S[k] for k in ("H", "W", "need", "sha", "read"))
READER = run_path(S["C"]["Q"] / "nvme_conversation/client_rows.py")["summarize"]
POWER = run_path(S["C"]["Q"] / "packed_nvme_manifest/server_profile/system_driver/review.py")[
    "power"
]


def check_public(r):
    need(
        r["classification"] == "MEDIDO_NO_PORTATIL"
        and [b["role"] for b in r["arms"]] == list(S["ORDER"]),
        "six ordered processes",
    )
    for src, h in r["sources"].items():
        need(sha(HERE / src) == h, "frozen file " + src)
    traj = r["arms"][0]["target_ids"]
    for arm in r["arms"]:
        need(arm["target_ids"] == traj and arm["maxima"]["swap_bytes"] == 0, "work or swap")
        for i, (n, cache, work) in enumerate(((2043, 0, 2043), (2105, 2044, 61)), 1):
            t = arm["turns"][i - 1]
            need(
                (t["prompt"], t["cached"], t["evaluated"]) == (n, cache, work)
                and t["output"] == t["predicted"] == traj[str(i)]["sampled"]
                and t["stop"] == "stop"
                and t["validator"] == "PASS"
                and 0
                < t["first_reasoning_s"]
                <= t["first_final_s"]
                <= t["transport_s"]
                <= t["valid_s"],
                "client geometry or clocks",
            )
    need(r["comparison"] == S["compare"](r["arms"]), "component comparison")


def run(root, ref):
    f = H["G"]["read"](root / "receipt.json", ref)
    need(f["status"] == "COMPLETE_CODE_CHAT" and len(f["arms"]) == 6, "closed family")
    workload = W["CodeChat"](root / "1R/raw/T1-input.json", sha, S["grader"], H["SESSION"].ids_hash)
    results = []
    for i, row in enumerate(f["arms"], 1):
        role, unit = row["role"], row["unit"]
        arm = root / (str(i) + role)
        raw = arm / "raw"
        rec = read(arm / "receipt.json")
        need(
            rec["status"] == "MEASURED" and rec["trial"] | dict(scope_s=rec["elapsed_s"]) == row,
            "frozen trial",
        )
        session = H["G"]["read"](arm / "session.json", row["session_sha256"])
        monitor = H["G"]["read"](raw / (unit + ".json"), session["monitor_sha256"])
        stderr = raw / (unit + ".stderr")
        need(
            all(
                sha(raw / (unit + suffix)) == digest
                for suffix, digest in monitor["output_sha256"].items()
            )
            and monitor["returncode"] == 0
            and monitor["mapped_libraries_match_ldd"]
            and monitor["stop_reason"] == "INTERRUPTED_BY_OWNER"
            and session["cleanup"] == "SERVER_EXIT_0_OWNER_STOP_UNIT_CLOSED_PORT_AVAILABLE",
            "producer and cleanup",
        )
        client = read(arm / "client-receipt.json")
        for j, cap in enumerate(workload.caps, 1):
            prompt = raw / f"T{j}-input.json"
            item = read(raw / f"T{j}-result.json")
            need(
                sha(prompt) == workload.digests[j - 1]
                and item == client["rows"][j - 1]
                and item["official_ids"] == workload.ids[j - 1],
                "official history",
            )
            rebuilt = READER(item, raw, j, ids_hash=H["SESSION"].ids_hash)
            need(rebuilt == row["turns"][j - 1], "SSE and validated clocks")
            need(
                W["serial"](
                    stderr.read_bytes(), j, rebuilt["output"], rebuilt["prompt"], cap, S["NATIVE"]
                )
                == row["target_ids"][str(j)],
                "native sequence",
            )
        need(
            S["grader"].grade(W["GRADER"], item["message"]["content"])["status"] == "PASS",
            "independent isolated validator",
        )
        window = read(raw / (unit + ".start-inventory.receipt.json"))
        limits = monitor["cgroup_end"]
        need(
            row["maxima"] == session["maxima"] == monitor["maxima"]
            and row["energy"] == session["energy"] == POWER(arm, row)
            and window["sha256"]
            == session["start_inventory"]
            == sha(raw / (unit + ".start-inventory.jsonl"))
            and window["duration_s"] == row["c118_s"]
            and row["c118_s"] >= 60
            and window["cap_bytes"] == limits["memory_high"] == limits["memory_max"] == 20 << 30
            and limits["swap_max"] == limits["events"]["oom"] == limits["events"]["oom_kill"] == 0,
            "resources",
        )
        need(
            H["read"](arm / "arm-inputs.json")["protocol_sha256"] == S["METHOD"]
            and H["read"](arm / "arm-inputs.json")["argv"] == monitor["command"],
            "process command",
        )
        results.append(dict(row, receipt_sha256=sha(arm / "receipt.json")))
    report = dict(
        classification="MEDIDO_NO_PORTATIL",
        commit=f["commit"],
        tree=f["tree"],
        sources={n: sha(HERE / n) for n in ("run.py", "workload.py", "protocol.md")},
        family_sha256=ref,
        window_sha256=f["window_sha256"],
        elapsed_s=f["elapsed_s"],
        arms=results,
        comparison=S["compare"](results),
        model_starts=6,
        requests=12,
        m3="PARTIAL",
        m4="NOT_MET",
    )
    need(all(report["comparison"][k] == f[k] for k in report["comparison"]), "family comparison")
    check_public(report)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family", type=Path)
    p.add_argument("--family-sha256")
    p.add_argument("--new-output-dir", type=Path)
    p.add_argument("--check", type=Path)
    a = p.parse_args()
    if a.check:
        check_public(read(a.check))
        print("PASS six natural code arms and clocks")
    else:
        a.new_output_dir.mkdir()
        try:
            r = run(a.family, a.family_sha256)
        except Exception as exc:
            S["publish"](
                a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc))
            )
            raise
        S["publish"](a.new_output_dir / "code-chat.json", r)
        print(r["comparison"]["decision"])
