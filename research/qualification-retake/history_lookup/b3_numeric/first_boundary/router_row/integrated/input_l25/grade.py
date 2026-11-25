"""Attribute the layer-25 operands only after the new observer reproduces the integrated ON."""

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import probes  # noqa: E402

# Load the master grading script under a unique name; it imports the canonical boundary schema.
integrated = probes.load(HERE.parent / "evaluate.py", "l25_integrated_comparison")
base = integrated.boundary
service = probes.load(integrated.FB.parent / "profile.py", "l25_numeric_parent")
official = probes.load(integrated.Q / "packed_nvme_manifest/capture_numeric/grade.py", "l25_c270")
sha, need = probes.sha, base.need
READ_ONLY = "65dc16c6c54994fec490b051584820098741b51ec4b02c814070ed540cd2d79a"


def read(p):
    return json.loads(p.read_bytes())


def pinned(file, h):
    need(sha(file) == h, "authority " + file.name)
    return read(file)


def gold_files(control):
    # The independent reference checks C270/C127's complete output-tree hash.
    cap = official.reference(control)
    anchors = pinned(HERE.parent / "source_l25/receipt.json", READ_ONLY)
    wanted = {(il, name) for il in (24, 25) for name in probes.GOLD}
    wanted.add((25, "ffn_moe_logits"))
    sites = {s.name: s for s in integrated.SITES}
    keys = {}
    with (cap / "index.tsv").open() as f:
        for r in csv.DictReader(f, delimiter="\t"):
            phase = r["phase"]
            layer, name = int(r["layer"]), r["name"]
            if phase not in ("decode0", "decode1") or (layer, name) not in wanted:
                continue
            pos = 189 + int(phase[-1])
            site = sites[name]
            file = cap / r["file"]
            need(
                file.parent == cap
                and file.is_file()
                and not file.is_symlink()
                and r["state_tokens"] == "1"
                and int(r["first_abs"]) == pos
                and r["type"] == "f32"
                and tuple(map(int, r["ne"].split(","))) == (*site.dims, 1, 1, 1)
                and int(r["bytes"]) == 4 * site.dims[0]
                and (pos, layer, name) not in keys,
                "C270 canonical singleton",
            )
            base.validate_words(file.read_bytes(), site)
            if layer == 25 and name in ("attn_post_norm", "ffn_moe_logits"):
                need(sha(file) == anchors["AR"][f"{pos}.{name}"], "independent C127/C270 anchor")
            keys[pos, layer, name] = file
    need(len(keys) == 10, "eight new AR singleton states plus two pre-bias products")
    return cap, keys


def paired_subset(old, new):
    need(set(old) <= set(new), "missing pre-existing observer name")
    changed = [k for k, v in old.items() if new[k] != v]
    need(not changed, f"nonneutral payloads {len(changed)}; first {changed[:1]}")


def inference(input_mismatches, output_mismatches):
    if input_mismatches:
        return "DIFFERENT_INPUT_AT_ROUTER"
    if output_mismatches:
        return "DIFFERENT_PRODUCT_WITH_IDENTICAL_INPUT"
    return "EQUAL_OBSERVED_OPERAND_AND_PRODUCT"


def compare(capture, reference_on, c270_dir, ar_capture):
    """Caller supplies the actual .capture directories, plus the full C270 family directory."""
    on_dir = reference_on.parents[1]
    family = pinned(on_dir.parent / "receipt.json", probes.FAMILY_SHA)
    on = pinned(on_dir / "receipt.json", family["arms"]["ON"]["receipt_sha256"])
    observed = pinned(on_dir / "comparison.json", on["comparison_sha256"])
    need(
        on["status"] == "OBSERVED_ON"
        and on["library_sha256"] == probes.IMAGE_SHA
        and on["build_sha256"] == probes.BUILD_SHA
        and reference_on == on_dir / "raw" / (on["unit"] + ".capture"),
        "old integrated ON lineage",
    )
    old_cuts = list(integrated.cuts("ON"))
    new_cuts = old_cuts + probes.sites()
    before = base.check_arm(reference_on, "B3", old_cuts)
    need(
        before == observed["coverage"]
        and before["payloads"] == 1149
        and observed["common_payloads"] == 885,
        "all old ON outputs",
    )
    after = base.check_arm(capture, "B3", new_cuts)
    need((after["payloads"], after["bytes"]) == (1182, 19_732_608), "closed new inventory")
    paired_subset(before["files_sha256"], after["files_sha256"])
    reference, files = gold_files(c270_dir)
    old_ar = integrated.reference(ar_capture.parents[2])
    need(old_ar["AR"] == ar_capture, "independent AR capture path")
    _, pins = service.raw_capture(c270_dir)
    ar_grade = service.require_arm(ar_capture, "AR", reference, pins["gold_full_logits_sha256"])
    current_grade = service.require_arm(capture, "B3", reference, pins["gold_full_logits_sha256"])
    need(
        ar_grade["prefix"] == current_grade["prefix"] == on["grade"]["prefix"],
        "all 2248 prefill files against C270 and AR",
    )
    for n, data in current_grade["states"].items():
        need(
            data == on["grade"]["states"][n] and data["sha256"] == sha(reference_on / n),
            "observational neutrality of " + n,
        )
    need(
        all(
            current_grade["states"][name] == ar_grade["states"][name]
            for name in ("initial-pool.bin", "initial-kv.bin")
        ),
        "AR state before B3",
    )
    vector_sha = {}
    for n in service.ROWS:
        pair = service.logits_grade.compare_rows(
            service.row(reference_on, n), service.row(capture, n)
        )
        need(
            pair["finite"]
            and pair["bitwise"]
            and pair["n_vocab"] == 201088
            and pair["reference_sha256"] == observed["logits"][n]["candidate_sha256"],
            "nonneutral complete logits " + n,
        )
        vector_sha[n] = pair["candidate_sha256"]
    # The old ON family already linked its 885 common rows to AR; recheck their actual files.
    common = base.check_arm(ar_capture, "AR")["files_sha256"]
    need(len(common) == 885, "common AR inventory")
    paired_subset(common, after["files_sha256"])
    by_name = {s.name: s for s in integrated.SITES}
    diff = {}
    for (p, il, name), file in sorted(files.items()):
        tensor = f"{name}-{il}"
        row = integrated.diff(
            file, capture / "boundary" / f"{p}.{tensor}.bin", p, il, name, by_name[name]
        )
        diff[f"{p}.{tensor}"] = row
    diagnosis = {}
    for pos in (189, 190):
        a = diff[f"{pos}.attn_post_norm-25"]["changed_words"]
        z = diff[f"{pos}.ffn_moe_logits-25"]["changed_words"]
        diagnosis[str(pos)] = inference(a, z)
    return {
        "status": "MEASURED_L25_INPUTS",
        "neutral": True,
        "coverage": {k: after[k] for k in ("payloads", "bytes", "geometry_sha256")},
        "identical_prior_on_payloads": 1149,
        "identical_common_ar_payloads": 885,
        "prefill": current_grade["prefix"],
        "state_sha256": current_grade["states"],
        "logits_sha256": vector_sha,
        "gold_rows": diff,
        "diagnosis": diagnosis,
        "pos191": "NO_INDEPENDENT_AR_ROWS_AT_THESE_SITES",
        "without_gold": {
            key: digest
            for key, digest in after["files_sha256"].items()
            if key not in before["files_sha256"] and key.removesuffix(".bin") not in diff
        },
        "source_l25_sha256": READ_ONLY,
    }
