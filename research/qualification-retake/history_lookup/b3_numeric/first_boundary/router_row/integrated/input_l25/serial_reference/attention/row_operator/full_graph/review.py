"""Reopen OFF and ON from raw inputs and report gate, numerical frontier, resources and energy."""

import argparse
import struct
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
F = run_path(str(HERE / "pair.py"))
KV = run_path(str(HERE.parents[4] / "kv/screen.py"))
G, P, R, M, S, read, need, sha, save = (
    F[k] for k in ("G", "P", "R", "M", "S", "read", "need", "sha", "save")
)


def summarize(grade):
    v = grade["vs_serial"]
    by_position = {}
    for pos in G["POS"]:
        by_position[str(pos)] = {
            r["tensor"]: r["changed_words"] for r in v["layer25"].values() if r["position"] == pos
        }
    return dict(
        status=grade["status"],
        earliest=v["first_by_position"],
        layer25_different_words=by_position,
        different_payloads=v["different_payloads"],
        equal_payloads=v["equal_payloads"],
        changed_top4=v["changed_routes"],
        masks=grade["masks"],
        post3_kv_equals_serial=grade["post3_kv_equals_serial"],
        states=grade["states"],
        prefix=grade["prefix"],
        full_logits=grade["full_logits"],
        attention_restored=grade["attention_restored"],
        full_numerical_gate=grade["all_covered_equal_to_serial"],
        checked_payloads=grade["checked_payloads"],
    )


def locate_kv(serial_capture, actual_capture, log):
    KV["source_and_log"](log.read_text())
    serial, layout = KV["parse"]((serial_capture / "post3-kv.bin").read_bytes(), 192)
    actual, other = KV["parse"]((actual_capture / "post3-kv.bin").read_bytes(), 192)
    need(layout == other, "logical KV layouts")
    delta = KV["contrast"](serial, actual)
    need(all(row["position"] >= 189 for row in delta["changes"]), "prefix KV changed")
    return {
        k: delta[k]
        for k in ("rows", "words", "changed_words", "changed_rows", "first", "first_per_position")
    }


def ordered_routes(serial_capture, actual_capture, changes):
    compared = {}
    for leaf, observation in changes.items():
        serial, actual = (
            struct.unpack("<4i", (root / "boundary" / leaf).read_bytes())
            for root in (serial_capture, actual_capture)
        )
        same_rank = sum(x == y for x, y in zip(serial, actual, strict=True))
        overlap = len(set(serial) & set(actual))
        need(
            len(set(serial)) == len(set(actual)) == 4
            and same_rank == 4 - observation["changed_words"],
            "ordered top-four witness",
        )
        compared[leaf] = {"identical_ranks": same_rank, "shared_experts": overlap}
    return compared


def review(a):
    r = R["reopen"](a.family, a.receipt_sha256)
    ctrl = R["reopen"](a.reference, R["NUMERIC"])
    parent = R["reopen"](a.parent, G["PARENT"])
    build = read(a.build / "receipt.json")
    need(
        sha(a.build / "receipt.json") == F["BUILD"] == r["build_sha256"]
        and build["status"] == "GO_INTEGRATED_ATTENTION_PAIR"
        and sha(a.build / "b3-numeric") == build["elf_sha256"]
        and sha(a.build / "libllama.so.0.0.9884") == build["image_sha256"]
        and sha(a.build / "boundary.cpp") == build["client_source_sha256"]
        and sha(a.build / "llama-graph.cpp") == build["graph_source_sha256"]
        and r["runner_sha256"] == sha(HERE / "pair.py")
        and r["grade_source_sha256"] == sha(HERE / "grade.py")
        and r["protocol_sha256"] == M["METHOD"] == sha(HERE / "protocol.md")
        and r["model_starts"] == 2
        and r["generation_requests"] == 0,
        "family provenance",
    )
    win = read(a.window / "receipt.json")
    need(
        win["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and win["gpu_driver"] == r["driver"]["release"]
        and sha(a.window / "receipt.json") == r["window_sha256"]
        and sha(a.window / "samples.jsonl") == win["window_sha256"],
        "resource admission",
    )
    refs = F["targets"](a.parent, parent)
    gold = a.reference / "raw" / (ctrl["unit"] + ".capture")
    pins = read(S["QUAL"] / "nvme_r0_gate/inputs/receipt.json")
    need(P["prepare"].tree_digest(gold) == pins["gold"], "C127/current R0")
    arms = {}
    for which in ("OFF", "ON"):
        directory = a.family / which
        unit = r["unit"] + "-" + which.lower()
        arm = r["arms"][which]
        cfg = read(directory / "full-resource.json")
        command = read(directory / "full-argv.json")
        m, launch, inv = F["audit"](directory, unit, cfg, command, which)
        need(
            cfg["pinned"]["numerical_dso_sha256"]["libllama.so.0.0.9884"] == build["image_sha256"]
            and cfg["pinned"]["capture_sha256"] == build["elf_sha256"]
            and cfg["native_variant"] == which
            and cfg["scientific_protocol_sha256"] == M["METHOD"]
            and arm["maxima"] == m["maxima"]
            and arm["model_s"] == m["elapsed_s"]
            and arm["scope_cleanup"]
            and inv == arm["c118"],
            "command and resource monitors",
        )
        observed = G["contrast"](directory / "raw" / (unit + ".capture"), which, refs, gold, pins)
        need(
            observed == read(directory / "grade.json")
            and observed["status"] == arm["status"]
            and sha(directory / "grade.json") == arm["grade_sha256"],
            "reconstructed judgments",
        )
        kv = locate_kv(
            refs["AR"],
            directory / "raw" / (unit + ".capture"),
            directory / "raw" / (unit + ".stderr"),
        )
        need(observed["post3_kv_equals_serial"] == (kv["changed_words"] == 0), "serialized KV link")
        arms[which] = dict(
            logical_kv=kv,
            routing=ordered_routes(
                refs["AR"],
                directory / "raw" / (unit + ".capture"),
                observed["vs_serial"]["changed_routes"],
            ),
            grade=summarize(observed),
            scope_s=arm["scope_s"],
            model_s=arm["model_s"],
            maxima=m["maxima"],
            c118=inv,
            live_samples=arm["samples_live"],
            gpu_energy=R["power"](directory, {"unit": unit}),
        )
    need(
        r["status"] == arms["ON"]["grade"]["status"]
        and arms["OFF"]["grade"]["status"] == "PASS_CONTEMPORARY_OFF",
        "OFF precedent",
    )
    return dict(
        status=r["status"],
        family_sha256=a.receipt_sha256,
        prior_sha256=G["PARENT"],
        r0_sha256=R["NUMERIC"],
        build_sha256=F["BUILD"],
        window_sha256=r["window_sha256"],
        model_sha256=r["model_sha256"],
        protocol_sha256=M["METHOD"],
        commit=r["commit"],
        tree=r["tree"],
        graph_sha256=build["image_sha256"],
        observer_sha256=build["elf_sha256"],
        build_s=build["wall_s"],
        driver=r["driver"],
        arms=arms,
        model_starts=2,
        generation_requests=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("family", "reference", "parent", "build", "window", "new-output-dir"):
        parser.add_argument("--" + k, type=Path, required=True)
    parser.add_argument("--receipt-sha256", required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    result = review(args)
    save(args.new_output_dir / "result.json", result)
    print(result["status"])
