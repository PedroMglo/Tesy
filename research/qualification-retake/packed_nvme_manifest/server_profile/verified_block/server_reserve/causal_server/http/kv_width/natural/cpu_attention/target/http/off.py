"""Qualify the new server ELF with every block switch disabled at the first natural T1 cut."""

import argparse
import os
import re
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
N = run_path(str(HERE.parent / "family.py"))
F, G, need, sha, save = (N[k] for k in ("F", "G", "need", "sha", "save"))
QUALIFIED = "aba8a61c990d7cfb699015e6fc4ee3d6d57b656415858c3e0a8642d2c45391bb"
METHOD = "72d1c32beabb4e256a4452084fea0bd06eeb57e65f3d28869302c43b4f157c9f"


def validate(a, out, r):
    h, tree = G["tree"](G["REPO"])
    need(
        h == a.commit
        and sha(HERE / "protocol.md") == METHOD
        and re.fullmatch(r"tesy-cpu-rows-[a-z0-9-]+", a.unit),
        "source or unit",
    )
    r.update(commit=h, tree=tree)
    base = G["read"](a.qualified / "receipt.json", QUALIFIED)
    need(
        base["status"] == "GO_CPU_ROWS_NATURAL_CUT_ONLY"
        and base["model_starts"] == 3
        and base["arms"]["ROWS"]["parity_vs_P"],
        "target cut",
    )
    build = G["read"](a.build / "receipt.json", N["BUILD"])
    client = G["read"](a.client / "receipt.json", F["CLIENT"])
    need(
        build["images"]["CPU"]["image_sha256"] == base["arms"]["ROWS"]["image_sha256"]
        and all(sha(Path(k)) == v for k, v in client["headers"].items()),
        "numerical ELF and client",
    )
    combo = client | {"arms": client["arms"] | {"WIDE": build["images"]["CPU"]}}
    prior = G["read"](a.previous / "receipt.json", F["F"]["F"]["GATE"])
    win = G["read"](a.window / "receipt.json", a.window_sha256)
    need(
        win["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and sha(a.window / "samples.jsonl") == win["window_sha256"],
        "C55",
    )
    policy, model_id = F["F"]["POST"].contract.placement(a.window, a.placement)
    ref = a.qualified / "P/raw" / (base["unit"] + "-p.capture")
    actual = {str(p.relative_to(a.qualified)): sha(p) for p in ref.iterdir() if p.is_file()}
    need(
        len(actual) == 13 and all(base["files"][k] == v for k, v in actual.items()),
        "independent serial witness",
    )
    arm = F["arm"](
        a, out / "OFF", "OFF", combo, prior, policy, model_id, study=METHOD, reference=ref
    )
    r.update(
        arm=arm,
        qualified_sha256=QUALIFIED,
        window_sha256=a.window_sha256,
        build_sha256=N["BUILD"],
        unit=a.unit,
    )
    return "GO_CPU_ELF_WITH_BLOCK_OFF"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "qualified",
        "build",
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
    r = dict(status="FAIL_PRESERVED", commit=a.commit, protocol_sha256=METHOD)
    try:
        r["status"] = validate(a, out, r)
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
