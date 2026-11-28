"""Reopen the two W controls of each conversation without loading weights."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
CPU = HERE.parent / "cpu_wave"
LOOK = run_path(CPU / "code_chat/lookup.py")
S = LOOK["S"]
need, sha, read, publish = (S[k] for k in ("need", "sha", "read", "publish"))


def prepare(nominal, code, out):
    families = {
        "nominal": (nominal, read(CPU / "decision.json")["client"]["receipt_sha256"], "ON"),
        "code": (code, read(CPU / "code_chat/code-chat.json")["family_sha256"], "W"),
    }
    witnesses, files = {}, {}
    for name, (family, seal, role) in families.items():
        need(sha(family / "receipt.json") == seal, "physical family")
        arms = read(family / "receipt.json")["arms"]
        fixed = None
        obs = []
        for i in (3, 4):
            trial = arms[i - 1]
            arm = family / (f"{i}-ON" if name == "nominal" else f"{i}W")
            need(trial["role"] == role, "pack and CPU fusion")
            session_sha = trial.get("native_sha256") or trial["session_sha256"]
            need(sha(arm / "session.json") == session_sha, "source session")
            entry, ticks, cut, interior = LOOK["evidence"](arm, trial)
            turn = trial["turns"][1]
            prompt_hash = S["H"]["SESSION"].ids_hash(entry["prompt"])
            need(
                turn["official_ids_sha256"] == prompt_hash
                and len(entry["target"]) == turn["output"] == (47 if name == "nominal" else 256)
                and turn["evaluated"] == (153 if name == "nominal" else 61)
                and turn["cached"] == 2044
                and turn["validator"] == "PASS"
                and cut == (44 if name == "nominal" else 84)
                and interior is not None,
                "target work and first final",
            )
            if fixed is None:
                fixed = entry
                for kind in ("prompt", "target"):
                    path = out / f"{name}-{kind}.i32"
                    raw = S["NATIVE"]["ids_bytes"](entry[kind])
                    with path.open("xb") as dest:
                        dest.write(raw)
                    files[path.name] = hashlib.sha256(raw).hexdigest()
            need(fixed == entry, "different supplied IDs across W controls")
            log = (arm / "raw" / (trial["unit"] + ".stderr")).read_bytes()
            start = [clock for clock, _, event in S["NATIVE"]["events"](log) if event == ("start",)][1]
            minutes, sec, ms, us = start
            start_ns = (((minutes * 60 + sec) * 1000 + ms) * 1000 + us) * 1000
            feed_ns = interior + start_ns - ticks[0]
            need(ticks[cut - 1] - ticks[0] <= feed_ns <= ticks[cut] - ticks[0], "first-final ordering")
            obs.append(dict(
                arm=i, session_sha256=session_sha, family_sha256=seal,
                prompt_sha256=prompt_hash, target_sha256=trial["target_ids"]["2"]["sampled_sha256"],
                cut=cut, feed_ns=feed_ns, ticks_ns=[n - ticks[0] for n in ticks],
                prefill_ns=round(turn["prefill_s"] * 1e9),
                first_final_ns=round(turn["first_final_s"] * 1e9),
                decode_ns=round(turn["decode_s"] * 1e9), valid_ns=round(turn["valid_s"] * 1e9),
            ))
        witnesses[name] = obs
    return dict(files=files, cases=witnesses, status="REPRODUCED_TARGET_INPUTS")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("nominal", "code", "new-output-dir"):
        p.add_argument("--" + arg, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        result = prepare(a.nominal, a.code, a.new_output_dir)
    except Exception as exc:
        publish(a.new_output_dir / "failure.json", {"status": "FAIL_PRESERVED", "reason": str(exc)})
        raise
    publish(a.new_output_dir / "receipt.json", result)
    print(result["status"])
