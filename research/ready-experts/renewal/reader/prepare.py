"""Select target-requested windows without inspecting the service times used for comparison."""

import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
BASE = run_path(HERE.parents[1] / "screen.py")
SRC, need = BASE["SOURCE"], BASE["require"]
MANIFEST = "cd4c0665c5485268cddfc7dba576b1cf490222c120cf34f72d555a6cbccbc5b9"
METHOD = "356d5492dc3270def61ca482972b8e55e1dfc8008cbbfac6e0e7eeec44029fc0"


def choose(rows):
    waves, _ = SRC["timeline"](rows)
    order = {SRC["key"](e): i for i, e in enumerate(rows) if e.kind == 11}
    picked = {}
    for w in waves:
        call, _, layer, _ = w.site
        if not 2 <= call <= 46:
            continue
        keys = sorted(w.reserved & w.demands, key=order.__getitem__)
        width = 4 if call == 2 else 1
        if len(keys) < width or (width == 1 and len(keys) != 1):
            continue
        label = width, "CPU" if layer < 25 else "CUDA0"
        picked.setdefault(label, (w.site, keys[:width]))
    return [picked[n, tier] for n in (4, 1) for tier in ("CPU", "CUDA0")]


def run(a):
    need(SRC["digest"](HERE / "protocol.md") == METHOD, "method")
    receipt = SRC["pinned"](a.manifest / "receipt.json", MANIFEST)
    idx = SRC["pinned"](a.manifest / "integral-index.json", receipt["index_sha256"])
    prior = SRC["pinned"](
        BASE["NATURAL"] / "prefill_retention/request_cost/receipt.json", BASE["PRIOR"]
    )
    population = None
    for label in ("P97", "P106"):
        BASE["read_arm"](a.archive, label, prior[label])
        name, sha, _ = SRC["SOURCES"][label]
        source = a.archive / ("part-" + label[1:]) / name
        if label == "P106":
            _, rows, _, _ = SRC["Q"]["read_new"](source, sha)
        else:
            rows, _ = SRC["T"]["PFJ"]["read_journal"](source / "ON/raw/events.pfj")
        arm = choose(rows)
        need(population is None or arm == population, "arms differ")
        population = arm
    experts = {(e["layer"], e["expert"]): e for e in idx["experts"]}
    need(len(experts) == 4608 and idx["weight_window"] == 13221888, "pack extent")
    text, ids = [], []
    for g, (site, keys) in enumerate(population):
        for k in keys:
            e = experts[k[0], k[3]]
            c = e["components"][:3]
            need(
                [x["packed_relative_offset"] for x in c] == [0, 4406400, 8812800]
                and all(x["type"] == "mxfp4" and x["size_bytes"] == 4406400 for x in c)
                and e["pack_offset"] % 4096 == 0,
                "target component geometry",
            )
            text.append("\t".join(map(str, [g, e["pack_offset"], *(x["sha256"] for x in c)])))
            ids.append([site, k])
    need(len(text) == 10, "workload size")
    plan = a.new_output_dir / "windows.tsv"
    plan.write_text("\n".join(text) + "\n")
    return {
        "status": "PASS",
        "schema": "tesy.ready_read_plan.v1",
        "method_sha256": METHOD,
        "source_sha256": SRC["digest"](Path(__file__)),
        "manifest_sha256": MANIFEST,
        "pack_stat": receipt["pack_stat"],
        "pack_path": receipt["pack_path"],
        "model_sha256": receipt["model_sha256"],
        "pack_sha256": receipt["pack_sha256"],
        "plan_sha256": SRC["digest"](plan),
        "source_sites_and_generations": ids,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "manifest", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a)
    except (OSError, ValueError, KeyError, AssertionError, TypeError) as e:
        result = {
            "status": "NOT_RUN_RAW_REQUIRED" if isinstance(e, FileNotFoundError) else "FAIL",
            "reason": str(e),
        }
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(result["status"], result.get("reason", ""))
    raise SystemExit(result["status"] != "PASS")
