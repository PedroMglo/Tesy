"""Run P, reproduce the known failing block, then enable CPU row attention at the identical cut."""

import argparse
import os
import re
import time
from functools import partial
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
E = run_path(str(HERE / "build.py"))
F, G, need, sha, save = (E[k] for k in ("F", "G", "need", "sha", "save"))
S = F["S"]
BUILD = "26de4923c71a3051352c4648059786ee52f0c3dc16d6d14a9806828663ecd7be"
NATURAL = E["B"]["NATURAL"]
ORDER = ("P", "B", "ROWS")


def authenticate_capture(a, old, trial, cap):
    hist = "P" if trial == "P" else "ON"
    path = a.natural / hist / "raw" / (old["unit"] + "-" + hist.lower() + ".capture")
    prefix = str(path.relative_to(a.natural)) + "/"
    frozen = {key[len(prefix) :]: h for key, h in old["files"].items() if key.startswith(prefix)}
    actual = {p.name: sha(p) for p in cap.iterdir() if p.is_file()}
    expected = {
        "entry.pool",
        "end.pool",
        "prefill.f32",
        "entry.f32",
        "native.json",
        *(f"step-{j}.f32" for j in range(3)),
        *(f"end-{j}.kv" for j in range(5)),
    }
    need(frozen.keys() == expected and actual == frozen, "reproduction of all saved control bytes")
    return len(actual)


def check(a, old, trial, evidence, cap, grade):
    layers = [
        (int(i), int(n))
        for i, n in re.findall(
            rb"^tesy_b3_built attention (\d+) (\d+)$",
            cap.with_suffix(".stderr").read_bytes(),
            re.M,
        )
    ]
    expected = range(0) if trial == "P" else range(25 if trial == "B" else 0, 36)
    need(layers == [(i, 2304) for i in expected], "built layer and KV width coverage")
    evidence.update(layers=[i for i, _ in layers], parity_vs_P=grade["passed"])
    if trial != "ROWS":
        evidence["reproduced_capture_files"] = authenticate_capture(a, old, trial, cap)
        need(grade["passed"] == (trial == "P"), "expected labelled control")


def evaluate(a, out, r):
    head, tree = G["tree"](G["REPO"])
    need(
        head == a.commit
        and sha(HERE / "protocol.md") == E["METHOD"]
        and re.fullmatch(r"tesy-cpu-rows-[a-z0-9-]+", a.unit),
        "sealed checkout and unit",
    )
    r.update(commit=head, tree=tree)
    win = G["read"](a.window / "receipt.json", a.window_sha256)
    need(
        win["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and sha(a.window / "samples.jsonl") == win["window_sha256"],
        "fresh C55",
    )
    policy, model_id = F["F"]["POST"].contract.placement(a.window, a.placement)
    image = G["read"](a.build / "receipt.json", BUILD)
    need(
        image["status"] == "GO_CPU_TARGET_ELF_ONLY"
        and image["protocol_sha256"] == E["METHOD"]
        and image["operator_sha256"] == E["OPERATOR"],
        "target ELF and operator",
    )
    client = G["read"](a.client / "receipt.json", F["CLIENT"])
    need(
        client["status"] == "GO_NATURAL_CLIENT_ONLY"
        and all(sha(Path(k)) == h for k, h in client["headers"].items()),
        "unchanged client",
    )
    need(
        image["images"]["CONTROL"]["image_sha256"] == client["arms"]["WIDE"]["image_sha256"],
        "independently reproduced WIDE",
    )
    composite = client | {"arms": client["arms"] | {"WIDE": image["images"]["CPU"]}}
    old = G["read"](a.natural / "receipt.json", NATURAL)
    prior = G["read"](a.previous / "receipt.json", F["F"]["F"]["GATE"])
    r.update(
        window_sha256=a.window_sha256,
        client_sha256=F["CLIENT"],
        old_family_sha256=NATURAL,
        target_elf=G["IMAGE"],
        intervention_sha256=image["images"]["CPU"]["image_sha256"],
    )
    for trial in ORDER:
        mode = "P" if trial == "P" else "ON"
        r["stage"] = trial
        evidence = {}

        arm = F["arm"](
            a,
            out / trial,
            mode,
            composite,
            prior,
            policy,
            model_id,
            study=E["METHOD"],
            extra_flags={E["SWITCH"]: "1"} if trial == "ROWS" else None,
            check=partial(check, a, old, trial, evidence),
        )
        r["arms"][trial] = arm | dict(
            status={
                "P": "PASS_SERIAL_CONTROL",
                "B": "PASS_REPRODUCED_NEGATIVE_CONTROL",
                "ROWS": "PASS_TARGET_PARITY" if evidence["parity_vs_P"] else "FAIL_TARGET_PARITY",
            }[trial],
            **evidence,
        )
        if trial == "ROWS":
            need(evidence["parity_vs_P"], "full target still differs after CPU row attention")
    return "GO_CPU_ROWS_NATURAL_CUT_ONLY"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "build",
        "natural",
        "previous",
        "static",
        "client",
        "window",
        "placement",
        "derived",
        "constructor",
        "new-output-dir",
    ):
        p.add_argument("--" + k, type=Path, required=True)
    for k in ("commit", "unit", "window-sha256"):
        p.add_argument("--" + k, required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    t = time.monotonic()
    r = dict(
        status="FAIL_PRESERVED",
        unit=a.unit,
        commit=a.commit,
        protocol_sha256=E["METHOD"],
        build_sha256=BUILD,
        arms={},
    )
    try:
        r["status"] = evaluate(a, out, r)
    except Exception as exc:
        r["error"] = f"{type(exc).__name__}: {exc}"
    r.update(
        wall_s=time.monotonic() - t,
        model_starts=len(list(out.rglob("*.launch.json"))),
        http_requests=0,
        files={str(k.relative_to(out)): sha(k) for k in sorted(out.rglob("*")) if k.is_file()},
    )
    save(out / "receipt.json", r)
    print(r["status"], r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
