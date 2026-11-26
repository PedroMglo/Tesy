"""Regrade both CPU processes from saved words, mappings and cgroup counters, without inference."""

import argparse
from pathlib import Path
from runpy import run_path

R = run_path(str(Path(__file__).with_name("run.py")))
need, sha, save = (R[k] for k in ("need", "sha", "save"))
PHYSICAL = "1aded710de81d0562f88d7c0dd02da893e04d118b4e7724bc3921d79f7d41fa6"


def review(build, physical):
    built, run = [
        R["G"]["read"](p / "receipt.json", h)
        for p, h in ((build, R["BUILD"]), (physical, PHYSICAL))
    ]
    for p, r in ((build, built), (physical, run)):
        found = {
            str(f.relative_to(p)): sha(f)
            for f in p.rglob("*")
            if f.is_file() and f != p / "receipt.json"
        }
        need(found == r["files"], "complete original artifact set")
    need(
        run["build_sha256"] == R["BUILD"]
        and built["natural_sha256"] == R["B"]["NATURAL"]
        and run["protocol_sha256"] == R["B"]["METHOD"]
        and run["status"] == "GO_CPU_ROW_OPERATOR_ONLY",
        "scientific chain",
    )
    arms = {}
    prior = None
    for key in ("1", "2"):
        base = physical / key
        argv = R["G"]["read"](base / "argv.json", run["files"][key + "/argv.json"])
        exe = Path(argv[-2])
        need(
            exe.name == "cpu-fixture"
            and sha(build / exe.name) == built["elf"]
            and "OMP_NUM_THREADS=8" in argv
            and Path(argv[-1]).parts[-3:] == (physical.name, key, "vectors")
            and "--unit=" + run["unit"] + "-" + key in argv,
            "original executable and threads",
        )
        item = R["native"](base, run["unit"] + "-" + key, built, exe)
        recorded = run["arms"][key]
        need(
            all(recorded[k] == v for k, v in item.items()) and item["passed"],
            "native repeat verdict",
        )
        need(prior is None or item["vectors"] == prior, "independent bitwise repeat")
        arms[key] = dict(peak_B=item["peak_B"], wall_s=recorded["wall_s"], mapped=item["providers"])
        prior = item["vectors"]
    return dict(
        decision=run["status"],
        natural_sha256=R["B"]["NATURAL"],
        build_sha256=R["BUILD"],
        physical_sha256=PHYSICAL,
        method_sha256=R["B"]["METHOD"],
        elf=built["elf"],
        cpu_dso=built["providers"]["libggml-cpu.so.0"]["sha256"],
        ops_cpp=built["cpu_source"],
        commit=run["commit"],
        tree=run["tree"],
        threads=8,
        arms=arms,
        model_starts=0,
        per_position_F32=4096,
        rows_vs_serial=run["arms"]["1"]["different_F32_by_position"],
        equal_finite_rows_words_per_run=len(R["CASES"]) * 3 * 4096,
        unique_output_files=len(prior),
        host_energy_J=None,
        wall_s=run["wall_s"],
        build_s=built["wall_s"],
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("build", "physical", "new-output-dir"):
        p.add_argument("--" + k, required=True, type=Path)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    save(a.new_output_dir / "result.json", review(a.build, a.physical))
