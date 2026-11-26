"""Run both matched cold orders with the existing physical C110 resource supervisor."""

import json
from datetime import datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
BASE = run_path(str(HERE.parent / "run.py"))
G = run_path(str(HERE / "grade.py"))
B = run_path(str(HERE / "build.py"))
need, sha, receipt, A = (BASE[k] for k in ("need", "sha", "receipt", "A"))


def freeze(a):
    need(a.build_sha256 == B["PARENT_BUILD"], "qualified heavy build")
    authority = json.loads((HERE.parent / "result.json").read_bytes())
    need(
        authority["decision"] == "GO_CONTROLLED_C110_COST"
        and authority["family_sha256"] == G["FAMILY"],
        "qualified cost gate",
    )
    state, bound, monitor, _ = BASE["freeze"](a, build_commit=authority["commit"])
    old_exe, _heavy, model, identity, plan, old, env, providers, paths, drivers = bound
    gold = G["reference"](a.numerical)
    build = receipt(a.price_build / "receipt.json", a.price_build_sha256)
    exe = a.price_build / "c110-price"
    need(
        build["status"] == "PASS_C110_PRICE_BUILD"
        and build["parent_build"] == a.build_sha256
        and build["commit"] == a.commit
        and build["tree"] == state["profile"]["tree"]
        and sha(exe) == build["binary_sha256"],
        "timed client identity",
    )
    first = json.loads((a.c55.parent / "samples.jsonl").read_text().splitlines()[0])["utc"]
    need(
        datetime.fromisoformat(first).timestamp()
        >= int(B["git"](HERE, "log", "-1", "--format=%ct", "--", "protocol.md")),
        "C55 predates cost protocol",
    )
    ce, libs, driver = A["SYS"]["system_loader"](exe, old, a.dso.resolve() / "objects")
    need(
        ce == env
        and set(libs) == paths
        and all(providers[k]["sha256"] == v for k, v in driver.items()),
        "timed ELF loader",
    )
    providers = providers | {
        str(exe): dict(stat=A["DEV"]["IO"].stat_id(exe), sha256=build["binary_sha256"])
    }
    state.update(
        numerical_sha256=G["FAMILY"],
        cost_build_sha256=a.price_build_sha256,
        providers=providers,
        cost_sources={
            n: sha(HERE / n) for n in ("protocol.md", "build.py", "grade.py", "run.py", "price.hpp")
        },
    )
    return (
        state,
        (old_exe, exe, model, identity, plan, old, env, providers, paths, drivers),
        monitor,
        (gold,),
    )


def evaluate(label, folder, _sys73, _model, _plan, gold):
    return G["grade"](label, folder, gold)


def run(a, out, r):
    BASE["run"](
        a,
        out,
        r,
        prepare=freeze,
        evaluate=evaluate,
        sources={k: (s, "OFF") for k, s in G["ORDER"].items()},
        prefix="tesy-ik-e10-price-",
        status="PASS_C110_MATCHED_PRICE",
        arm_status="PASS_C110_PRICE_ARM",
    )
    if r["status"] == "PASS_C110_MATCHED_PRICE":
        arms = {
            k: receipt(out / k / "receipt.json", v["receipt_sha256"]) for k, v in r["arms"].items()
        }
        r.update(G["compare"](arms))


if __name__ == "__main__":
    raise SystemExit(BASE["main"](run, ("numerical", "price-build"), ("price-build-sha256",)))
