"""Reopen the sealed natural T1 captures and compare distributions, KV and monitor evidence."""

import argparse
import math
import re
import struct
from pathlib import Path
from runpy import run_path

F = run_path(str(Path(__file__).with_name("family.py")))
G, S, C, sha, need, read = (F[k] for k in ("G", "S", "C", "sha", "need", "read"))
RECEIPTS = (
    "3b281685418808cb9d8e099e8c16ef59f6a0a9a1d6a16a5fb3846ab3e19f4098",
    "30fe606906a7b8862c7ba09d1832fdec0a04c50b3567a933abb38079176cc148",
    "1021eacad33871cdc44840a71556dfc860a310b16af24c5fc10175b28441e7f2",
    "fd3c914c4ba7cf238d2b2a86b496dc689dc163ccdb461fbaf7257695ff3bea2d",
    "ad8c82c323975f8ef31d68ae7d66a26b7de9c154f29a0d20aa405482428e9cc7",
    "808bc4223c610803a5e7adcf4e5cb687828f60fb5723a12a4829cf99774d94e1",
)


def verify_files(root, receipt):
    found = {
        str(p.relative_to(root)): sha(p)
        for p in root.rglob("*")
        if p.is_file() and p != root / "receipt.json"
    }
    need(found == receipt["files"], "whole artifact tree")


def compare_rows(capture, reference):
    rows = {}
    for name in ("prefill", "entry", "step-0", "step-1", "step-2"):
        left = (reference / (name + ".f32")).read_bytes()
        right = (capture / (name + ".f32")).read_bytes()
        need(len(left) == len(right) == 4 * 201088, "vocabulary")
        for blob in (left, right):
            need(
                all(math.isfinite(x) for (x,) in struct.iter_unpack("<f", blob)),
                "non-finite logits",
            )
        rows[name] = sum(
            a != b
            for a, b in zip(
                struct.iter_unpack("<I", left), struct.iter_unpack("<I", right), strict=True
            )
        )
    return rows


def localize_kv(candidate, reference, count, cut):
    kv = S["RB"]["SWA"]["KV"]

    def payload(directory):
        shards = sorted(directory.glob("end-*.kv"))
        blob = b"".join(s.read_bytes() for s in shards)
        banks = kv["layers_from_log"](directory.with_suffix(".stderr").read_bytes())
        offsets, headers = kv["parse"](blob, count, banks)
        return memoryview(blob), offsets, headers

    left, lo, lh = payload(reference)
    right, ro, rh = payload(candidate)
    need(
        lo == ro and lh == rh and all(left[o : o + n] == right[o : o + n] for o, n in lh),
        "KV layout or cell identity",
    )
    population = {"prefix": 0, "block": 0}
    changed = {}
    nz = zero_sign = nonfinite = 0
    for (bank, kind, layer, pos), offset in lo.items():
        which = "prefix" if pos < cut else "block"
        population[which] += 1
        a, b = left[offset : offset + 1024], right[offset : offset + 1024]
        if a == b:
            continue
        category = changed.setdefault(which, {})
        key = category.setdefault(str(layer), {})
        row = key.setdefault(f"{bank}_{kind}_{pos}", 0)
        for (x,), (y,) in zip(
            struct.iter_unpack("<H", a), struct.iter_unpack("<H", b), strict=True
        ):
            if x == y:
                continue
            row += 1
            if (x & 0x7C00) == 0x7C00 or (y & 0x7C00) == 0x7C00:
                nonfinite += 1
            elif (x & 0x7FFF) == (y & 0x7FFF) == 0:
                zero_sign += 1
            else:
                nz += 1
        key[f"{bank}_{kind}_{pos}"] = row
    return dict(
        population=population,
        differing_F16_by_layer_kind_position=changed,
        unequal_finite=nz,
        sign_of_zero=zero_sign,
        nonfinite_in_changed_pairs=nonfinite,
    )


def process(root, mode, reference, work, unit, *, label=None):
    label = label or mode
    folder = root / label
    unit += "-" + label.lower()
    raw = folder / "raw"
    launch = read(raw / (unit + ".launch.json"))
    monitor = read(raw / (unit + ".json"))
    args = read(folder / "invocation.json")
    capture = raw / (unit + ".capture")
    grade = F["grade"](capture, reference, work, mode)
    need(grade == read(folder / "grade.json"), "live grade")
    cfg = read(folder / "natural-resource.json")
    need(
        monitor["process_identity"] == launch["process_identity"]
        and monitor["limits"]["resource_protocol_sha256"]
        == launch["resource_protocol_sha256"]
        == sha(folder / "natural-resource.json")
        and monitor["command"] == args["command"][-5:]
        and monitor["explicit_env"] == args["expected"]
        and monitor["returncode"] == 0
        and monitor["stop_reason"] is None
        and monitor["mapped_libraries_match_ldd"]
        and not monitor["maxima"]["swap_bytes"],
        "target ownership, resources and exit",
    )
    inv = S["PK"]["PK"]["compact"].validate_inventory(
        folder, unit, dict(native_explicit_env=args["expected"]), launch
    )
    widths = [
        int(n)
        for n in re.findall(
            rb"^tesy_b3_built attention 25 (\d+)$", (raw / (unit + ".stderr")).read_bytes(), re.M
        )
    ]
    need(
        (bool(widths) and set(widths) == {2304}) if mode == "ON" else not widths,
        "graph width and ablation",
    )
    energy = run_path(str(C["Q"] / "packed_nvme_manifest/server_profile/system_driver/review.py"))[
        "power"
    ](folder, dict(unit=unit))
    before, after = grade["store_entry"], grade["store_end"]
    return dict(
        decision=grade["passed"],
        model_s=monitor["elapsed_s"],
        maxima=monitor["maxima"],
        energy=energy,
        inventory=inv,
        reserve=cfg["output_reserve"],
        logits_different_words_vs_P=compare_rows(capture, reference),
        logits_words_per_row=201088,
        entry=grade["entry"],
        end=grade["end"],
        kv_new_rows=grade["new_kv_rows"],
        prefix_ids=len(work["prefix"]),
        confirmed_ids=grade["confirmed"],
        L25_widths=widths,
        entry_pool_equal=(reference / "entry.pool").read_bytes()
        == (capture / "entry.pool").read_bytes(),
        exit_pool_equal=(reference / "end.pool").read_bytes()
        == (capture / "end.pool").read_bytes(),
        expert_store_delta={k: after[k] - v for k, v in before.items()},
        kv_shards_different=[
            k for k, v in grade["comparison"].items() if k.endswith(".kv") and not v
        ],
    )


def review(folders):
    pilot, client, busy, refused, window, physical = folders
    records = [G["read"](p / "receipt.json", h) for p, h in zip(folders, RECEIPTS, strict=True)]
    fail, built, c55fail, unopened, c55, target = records
    for i in (0, 1, 3, 5):
        verify_files(folders[i], records[i])
    for root, item in ((busy, c55fail), (window, c55)):
        need(
            sha(root / "samples.jsonl") == item["window_sha256"]
            and sha(root / "resource-policy.json") == item["canonical_policy_sha256"],
            "C55 evidence",
        )
    need(
        fail["status"] == "FAIL_PRESERVED"
        and built["status"] == "GO_NATURAL_CLIENT_ONLY"
        and built["elf_sha256"] == sha(client / "b3-numeric"),
        "client attempts",
    )
    need(
        c55fail["status"] == "NOT_ADMITTED"
        and c55fail["concurrent"] == ["cc1plus"]
        and unopened["model_starts"] == 0
        and unopened["status"] == "FAIL_PRESERVED",
        "rejected preliminary window",
    )
    need(
        c55["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and target["window_sha256"] == RECEIPTS[4]
        and target["client_sha256"] == RECEIPTS[1],
        "admission and client identity",
    )
    work = G["read"](client / "work.json", built["work_sha256"])
    reference = physical / "P/raw" / (target["unit"] + "-p.capture")
    modes = [mode for mode in F["CASES"] if (physical / mode / "grade.json").is_file()]
    arms = {mode: process(physical, mode, reference, work, target["unit"]) for mode in modes}
    need(
        list(modes) == ["P", "OFF", "ON"]
        and arms["P"]["decision"]
        and arms["OFF"]["decision"]
        and not arms["ON"]["decision"]
        and target["stage"] == "ON"
        and set(target["arms"]) == {"P", "OFF"}
        and target["model_starts"] == 3
        and target["status"] == "FAIL_PRESERVED",
        "order and stop at numerical mismatch",
    )
    cut = len(work["prompt"]) + len(work["prefix"]) - 1
    loc = localize_kv(
        physical / "ON/raw" / (target["unit"] + "-on.capture"), reference, cut + 3, cut
    )
    for mode in target["arms"]:
        saved = target["arms"][mode]
        need(
            saved["maxima"] == arms[mode]["maxima"]
            and saved["inventory"] == arms[mode]["inventory"]
            and saved["observed_L25_widths"] == arms[mode]["L25_widths"],
            "independent live proof",
        )
    return dict(
        decision="NO_GO_EXACT_NATURAL_BLOCK",
        status=target["status"],
        kv_difference=loc,
        error=target.get("error"),
        actual_arms=modes,
        arms=arms,
        receipts_sha256=RECEIPTS,
        commit=target["commit"],
        tree=target["tree"],
        model_starts=target["model_starts"],
        http_requests=0,
        wall_s=target["wall_s"],
        protocol_sha256=C["METHOD"],
        work_sha256=built["work_sha256"],
        reserve_order=[1, 1, 3],
        previous_attempts=["compile failure", "C55 cc1plus / zero launches"],
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--folders", type=Path, nargs=6, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    F["save"](a.new_output_dir / "result.json", review(a.folders))
