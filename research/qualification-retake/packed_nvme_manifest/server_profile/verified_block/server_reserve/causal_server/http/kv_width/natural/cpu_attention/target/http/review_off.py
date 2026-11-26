"""Reopen the stopped preflight, both observer fixtures and the sealed serial target control."""

import argparse
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
OFF = run_path(str(HERE / "off.py"))
A = run_path(str(HERE.parents[2] / "review.py"))
G, F, need, sha, save = (OFF[k] for k in ("G", "F", "need", "sha", "save"))
PINS = (
    "f1af9bfbd6d6dd9d3b69eb4971cf174e054ff92f5db3d724fc94917d03160b9b",
    "eabf06e6e4bd7214d361021af25e684003e8c109b274b0655708db984ad3004a",
    OFF["PROBE"],
    "b3ce96eaa059ccf80f5567981fa0eb27b8420ff490ad70c7e6e52b6e737f0ec0",
    "8ba42406e1ebd8e81b7cde38df0ab723b812e6e92286e9f132e1d922843c23e3",
)


def review(dirs, reference, client):
    records = [G["read"](d / "receipt.json", h) for d, h in zip(dirs, PINS, strict=True)]
    failed, missed, fixture, window, passed = records
    for i in (0, 1, 2, 4):
        A["verify_files"](dirs[i], records[i])
    need(
        sha(dirs[3] / "samples.jsonl") == window["window_sha256"]
        and sha(dirs[3] / "resource-policy.json") == window["canonical_policy_sha256"]
        and passed["window_sha256"] == PINS[3],
        "resource window",
    )
    need(
        failed["model_starts"] == 1
        and failed["http_requests"] == 0
        and failed["error"] == "ValueError: unexpected mapped ELF: ld.so.cache"
        and not list(next((dirs[0] / "OFF/raw").glob("*.capture")).iterdir()),
        "early failure",
    )
    need(
        missed["error"] == "ValueError: one real passive data mapping"
        and missed["files"] == {}
        and fixture["failed_sha256"] == PINS[0]
        and fixture["protocol_sha256"] == missed["protocol_sha256"]
        and len(fixture["rejected"]) == 10
        and all(fixture["rejected"].values()),
        "observer trials",
    )
    before, after = [
        F["read"](dirs[4] / ("loader-data-" + phase + ".json")) for phase in ("before", "after")
    ]
    need(
        before == fixture["cache"] | {"observed_cuts": 0}
        and after == before | {"observed_cuts": after["observed_cuts"]}
        and after["observed_cuts"] >= 0,
        "observer host identity",
    )
    old = G["read"](reference / "receipt.json", OFF["QUALIFIED"])
    ref = reference / "P/raw" / (old["unit"] + "-p.capture")
    for p in ref.iterdir():
        need(sha(p) == old["files"][str(p.relative_to(reference))], "reference capture")
    built = G["read"](client / "receipt.json", F["CLIENT"])
    work = G["read"](client / "work.json", built["work_sha256"])
    arm = A["process"](dirs[4], "OFF", ref, work, passed["unit"])
    need(
        passed["status"] == "GO_CPU_ELF_WITH_BLOCK_OFF"
        and passed["model_starts"] == 1
        and passed["http_requests"] == 0
        and passed["loader_probe_sha256"] == PINS[2]
        and all([arm["decision"], arm["entry_pool_equal"], arm["exit_pool_equal"]])
        and not any(arm["logits_different_words_vs_P"].values())
        and not arm["kv_shards_different"]
        and arm["maxima"] == passed["arm"]["maxima"]
        and arm["inventory"] == passed["arm"]["inventory"]
        and passed["arm"]["image_sha256"] == old["arms"]["ROWS"]["image_sha256"],
        "ablation validation",
    )
    return dict(
        status=passed["status"],
        protocol_sha256=OFF["METHOD"],
        qualified_sha256=OFF["QUALIFIED"],
        inputs_sha256=PINS,
        physical_commit=passed["commit"],
        physical_tree=passed["tree"],
        model_starts=2,
        http_requests=0,
        first_start=failed["error"],
        first_start_wall_s=failed["wall_s"],
        first_fixture=missed["error"],
        observer_sha256=fixture["cache"]["sha256"],
        rejected=fixture["rejected"],
        observed_data_cuts=after["observed_cuts"],
        arm=arm,
        wall_s=passed["wall_s"],
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--folders", nargs=5, required=True, type=Path)
    for name in ("reference", "client", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    save(a.new_output_dir / "result.json", review(a.folders, a.reference, a.client))
