"""Reopen original CUDA journals and both full logit files, including the historical banks."""

import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
R = run_path(str(HERE / "run.py"))
G, A, load, sha, need = (R[k] for k in ("G", "A", "load", "sha", "need"))


def review(family, digest, older, tiny):
    r = load(family / "receipt.json", digest)
    need(r["status"] == "PASS_TINY_GRAPH_BANK_INPUT" and not r["swap_peak_B"], "family")
    original = load(older / "receipt.json", R["HIST"])
    need(sha(tiny) == R["D"]["TINY"] and r["authority"]["historical_sha256"] == R["HIST"], "inputs")
    files = {
        str(p.relative_to(family)): sha(p)
        for p in family.rglob("*")
        if p.is_file() and p != family / "receipt.json"
    }
    need(files == r["raw_sha256"], "family raw inventory")
    arms = {}
    for mode in ("RESIDENT", "DIRECT", "PREAD_RANDOM"):
        arm = r["arms"][mode]
        need(
            arm["starts"] == 1
            and arm["observed_handoffs"] == 3
            and arm["child_gone"]
            and arm["returncode"] == 0
            and arm["sampled_vram_mib_max"] < R["D"]["VRAM"],
            "physical arm",
        )
        d = family / mode
        raw, log = (d / "stdout").read_text(), (d / "stderr").read_text()
        name = "RESIDENT" if mode == "RESIDENT" else "BANK9"
        origin = older / name
        for f in ("stdout", "stderr", "native/prefill.f32", "native/teacher.f32"):
            need(sha(origin / f) == original["raw_sha256"][name + "/" + f], "historical raw")
        old = R["SYS73"]["arm_grade"](name, origin)
        need(old == original["arms"][name]["grade"], "historical grade")
        view, source = (
            (raw, None) if mode == "RESIDENT" else A["audit"](raw, mode, d / "native", tiny)
        )
        grade = G["check_arm"](name, view, log, d / "native")
        need(
            grade == old == arm["grade"]
            and A["schedule"](raw) == A["schedule"]((origin / "stdout").read_text()),
            "schedule/grade changed",
        )
        comparison = G["compare_arms"](origin / "native", old, d / "native", grade)
        need(
            comparison == arm["historical"]
            and comparison["bitwise"]
            and comparison["routes_equal"],
            "reference logits or routes",
        )
        need(
            R["SYS73"]["placement"](origin / "stdout") == R["SYS73"]["placement"](d / "stdout"),
            "consumer placement",
        )
        if source:
            need(json.loads(json.dumps(source)) == arm["physical_source"], "source audit")
        arms[mode] = dict(
            physical_source=source,
            distinct_consumer_sites=grade["consumer_ops"],
            logits_sha256=grade["logits_sha256"],
            ordered_top4_sha256=grade["ordered_top4_sha256"],
            bank=grade["reconciled"],
            sampled_peak_vram_MiB=arm["sampled_vram_mib_max"],
        )
    for f in ("prefill.f32", "teacher.f32"):
        rows = [(family / m / "native" / f).read_bytes() for m in arms]
        need(rows[0] == rows[1] == rows[2], "contemporary full logits")
    need(
        len({tuple(sorted(v["ordered_top4_sha256"].items())) for v in arms.values()}) == 1,
        "quartets",
    )
    return dict(
        decision="GO_C110_SOURCE_PARITY",
        evidence="MEDIDO",
        family_sha256=digest,
        historical_family_sha256=R["HIST"],
        commit=r["authority"]["commit"],
        tree=r["authority"]["tree"],
        build_sha256=r["authority"]["build_sha256"],
        c55_sha256=r["authority"]["c55_sha256"],
        model_sha256=sha(tiny),
        starts=3,
        forwards=6,
        product_requests=0,
        real_120B_forwards=0,
        equal_finite_F32=1056,
        equal_ordered_quartets=66,
        arms=arms,
        scope_peak_B=r["memory_peak_B"],
        swap_peak_B=r["swap_peak_B"],
        energy_J=None,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("family", "historical", "tiny", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    result = review(a.family, a.family_sha256, a.historical, a.tiny)
    (a.new_output_dir / "result.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n"
    )
    print(result["decision"])
