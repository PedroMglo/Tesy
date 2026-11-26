"""Reopen the calibrated processes and measure residence at matching confirmed depths."""

import argparse
import struct
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
F = run_path(str(HERE.parent / "family.py"))
B, G, R, need, sha, read, save = (F[k] for k in ("B", "G", "R", "need", "sha", "read", "save"))


SHARED = run_path(str(HERE.parent / "live_prefix/review.py"))


def pool(path):
    data = path.read_bytes()
    words = iter(struct.unpack(f"<{len(data) // 8}Q", data))

    def vector():
        n = next(words)
        need(n <= 1024, "bounded vector")
        return tuple(next(words) for _ in range(n))

    need((next(words), next(words)) == (40, 36), "native slot count")
    layers = []
    for i in range(36):
        need((next(words), next(words)) == (i, 128), "layer metadata")
        state, expert, generation, claimed, last, hot, seen = [vector() for _ in range(7)]
        counter = next(words)
        keep = vector()
        plan = tuple(next(words) for _ in range(3))
        wave = vector()
        real = [e for e in expert if e != 2**64 - 1]
        need(
            all(len(v) == 40 for v in (state, expert, generation, claimed, last, keep))
            and not any(claimed)
            and len(real) == len(set(real))
            and all(0 <= e < 128 for e in real),
            "drained native layer",
        )
        layers.append(
            dict(
                expert=expert,
                generation=generation,
                last=last,
                real=set(real),
                policy=(hot, seen, counter, keep, plan, wave),
            )
        )
    need(next(words, None) is None, "complete pool")
    return layers


def footprint(a, b):
    serial, actual = pool(a), pool(b)
    out = {}
    for name, selected in (("CPU", range(25)), ("CUDA", range(25, 36))):
        different_slots = changed_gen = only_actual = only_serial = changed_recency = (
            changed_policy
        ) = 0
        for i in selected:
            x, y = serial[i], actual[i]
            different_slots += sum(p != q for p, q in zip(x["expert"], y["expert"], strict=True))
            changed_gen += sum(
                p != q for p, q in zip(x["generation"], y["generation"], strict=True)
            )
            changed_recency += sum(p != q for p, q in zip(x["last"], y["last"], strict=True))
            only_actual += len(y["real"] - x["real"])
            only_serial += len(x["real"] - y["real"])
            changed_policy += int(x["policy"] != y["policy"])
        out[name] = dict(
            slots=len(selected) * 40,
            different_slot_expert=different_slots,
            different_generation=changed_gen,
            only_candidate_resident=only_actual,
            only_serial_resident=only_serial,
            different_last_use=changed_recency,
            layers_with_different_policy=changed_policy,
        )
    return out


def review(a):
    r = R["reopen"](a.family, a.family_sha256)
    b = read(a.build / "receipt.json")
    need(
        sha(a.build / "receipt.json") == r["build_sha256"] == F["LIVE_ROLLBACK_BUILD"]
        and sha(a.build / "b3-numeric") == b["elf_sha256"]
        and sha(a.build / "libllama.so.0.0.9884") == b["image_sha256"]
        and (a.build / "rollback.cpp").read_text() == B["source"](False, False, True)
        and SHARED["source_hash"](r["commit"], "../grade.py") == r["grader_sha256"]
        and SHARED["source_hash"](r["commit"], "../family.py") == r["runner_sha256"]
        and sha(HERE / "protocol.md") == r["protocol_sha256"] == B["LIVE_ROLLBACK_METHOD"]
        and r["status"] == "GO_GREEDY_ROLLBACK_AND_CONTINUATION"
        and r["model_starts"] == 4
        and r["generation_requests"] == 0,
        "sealed supervisor, client and graph",
    )
    serial, official, _, _, _, _ = F["sources"](a)
    need(r["live_control_sha256"] == F["LIVE_CONTROL"], "live control identity")
    live = R["reopen"](a.live_control, r["live_control_sha256"])
    for case in ("AR", "B3"):
        need(live["arms"][case]["status"] == "PASS_" + case, "live bridge")
        prev = F["capture"](a.live_control, live["unit"], case)
        for file, old in (
            ("entry.kv", "initial-kv.bin"),
            ("entry.pool", "initial-pool.bin"),
            ("prefill.f32", "prefill_final.logits.f32"),
        ):
            need(sha(prev / file) == sha(official / old), "live prefix content")
    ar = F["capture"](a.family, r["unit"], "AR")
    win = read(a.window / "receipt.json")
    need(
        sha(a.window / "receipt.json") == r["window_sha256"]
        and sha(a.window / "samples.jsonl") == win["window_sha256"]
        and win["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and win["gpu_driver"] == r["driver"]["release"],
        "C55",
    )
    arms = {}
    for mode in G["CASES"]:
        root = a.family / mode
        cap = F["capture"](a.family, r["unit"], mode)
        unit = r["unit"] + "-" + mode.lower()
        entry = r["arms"][mode]
        cfg = read(root / "rollback-resource.json")
        m, launch, inv = F["audit"](root, unit, mode, cfg, read(root / "rollback-argv.json"))
        need(
            entry["scope_cleanup"]
            and 0 <= entry["c55_age_s"] < 3600
            and entry["samples_live"] > 0
            and m["elapsed_s"] == entry["model_s"]
            and m["maxima"] == entry["maxima"]
            and entry["c118"] == inv
            and cfg["pinned"]["capture_sha256"] == b["elf_sha256"]
            and entry["loaded"]["initialized"]["libllama.so.0.0.9884"] == b["image_sha256"],
            "process and resource bridge",
        )
        grade = G["compare"](cap, mode, official, serial, ar, live=True)
        grade["kv_coverage"] = F["live_coverage"](cap, mode)
        need(
            grade == read(root / "grade.json")
            and sha(root / "grade.json") == entry["grade_sha256"]
            and grade["status"] == entry["status"],
            "arm grade",
        )
        delta = {}
        if mode != "AR":
            n = grade["decision"]["accepted"] + 1
            for j, key in enumerate(("trim", "next-0", "next-1")):
                delta[key] = footprint(ar / f"keep-{n + j}.pool", cap / (key + ".pool"))
        arms[mode] = dict(
            grade=grade,
            pool_at_same_depth=delta,
            maxima=m["maxima"],
            scope_s=entry["scope_s"],
            model_s=entry["model_s"],
            c118=inv,
            provider_observations=entry["samples_live"],
            energy=R["power"](root, {"unit": unit}),
        )
    return dict(
        status=r["status"],
        arms=arms,
        model_starts=r["model_starts"],
        generation_requests=r["generation_requests"],
        commit=r["commit"],
        tree=r["tree"],
        protocol_sha256=r["protocol_sha256"],
        build_sha256=r["build_sha256"],
        parent_sha256=r["target_sha256"],
        serial_sha256=r["serial_sha256"],
        family_sha256=a.family_sha256,
        window_sha256=r["window_sha256"],
        model_sha256=r["model_sha256"],
        elf_sha256=b["elf_sha256"],
        library_sha256=b["image_sha256"],
        live_control_sha256=r["live_control_sha256"],
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "family",
        "target",
        "serial",
        "reference",
        "build",
        "window",
        "live-control",
        "new-output-dir",
    ):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    result = review(a)
    save(a.new_output_dir / "result.json", result)
    print(result["status"])
