"""Evaluate a fixed C286 decayed prefix feature against the observed C294 decode."""

import argparse
import json
from hashlib import sha256
from pathlib import Path

from cache_bound import EXPERT_BYTES, LINK_BPS, MAX_LOADS, STEPS, minimum, read_arm
from causal_prefix import top40

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
C286 = "c286-logical-route-policy-cost-20261006"
C294 = "c294-feature-ready-service-window-20261006"
PINS = {
    C286: "310d7844e5c941d4a2c011c1ef9cf69218db9459d873cf1f449ea61b17cacd47",
    C294: "5a689ed0c3e7e328973a12de229c3a6ff4e151c14d568d49e517ff7dee98fd84",
}
RULE_PIN = "a2a66aa6c81fa62b6199ba201f241868e766a90af31edf2319990077cb7c1da4"
INPUT_PIN = "ffcd2da79b579960cf43cfb3f696de6f48d50723cfa77ef36a9d5e7fbd48d14a"
CLOCK_PIN = "68fc5aa861cd51b1a1c19d693a1b40ebfe244c3f2bebc25b90be2fed4250208e"


def require(ok, label):
    if not ok:
        raise ValueError(label)


def digest(blob):
    return sha256(blob).hexdigest()


def encoded(value):
    return json.dumps(value, separators=(",", ":")).encode()


def audit(raw_root, backend):
    require(digest((HERE / "cross_prefix.md").read_bytes()) == RULE_PIN, "screen protocol changed")
    require(digest((backend / "src/c284-logical-route.h").read_bytes()) == CLOCK_PIN, "clock pin")
    dev = next((REPO / "results").glob("c276-*/development-inputs.json")).read_bytes()
    require(digest(dev) == INPUT_PIN, "input pin")
    fixture = json.loads(dev)
    manifest = {}
    for family, pin in PINS.items():
        blob = (REPO / "results" / family / "raw-manifest.json").read_bytes()
        require(digest(blob) == pin, "raw manifest pin")
        manifest.update({r["path"]: r for r in json.loads(blob)["files"]})

    def read(family, filename):
        relative = Path(family) / "raw" / filename
        blob = (raw_root / relative).read_bytes()
        entry = manifest["results/" + str(relative)]
        require(
            (len(blob), digest(blob)) == (entry["bytes"], entry["sha256"]),
            "native artifact mismatch",
        )
        return blob

    arms = {}
    for case, index in (("nominal153", 2), ("code153", 6)):
        source = f"c286-{index}-logical.native"
        snapshot = read(C286, source + "/initial.json")
        initial = json.loads(snapshot)
        original = json.loads(read(C286, source + "/result.json"))
        clock = json.loads(read(C286, source + "/logical-policy.json"))
        require(
            clock["enabled"]
            and original["initial"] == initial
            and original["initial_prefix_mode"] == 0
            and original["case"] == case
            and original["profile"] == "E"
            and original["mode"] == 2,
            "C286 provenance",
        )
        ids, cont = fixture[case]["ids"], fixture[case]["continuation_ids"]
        require(
            original["official_input_ids"] == ids
            and original["teacher_forced_ids"] == cont
            and initial["pending_queue"] == 0,
            "source input or phase",
        )
        require(
            all(
                row["rows"] == len(ids) + 32 and row["decay_epoch"] == row["rows"] // 64
                for row in clock["layers"][:35]
            )
            and clock["layers"][35]["rows"] == 41,
            "source coverage witness",
        )
        layer_rows = initial["layers"]
        require([row["layer"] for row in layer_rows] == list(range(36)), "source layers")
        selections = [top40(row["route_hotness"]) for row in layer_rows]
        e_logits = digest(read(C286, source + "/all33.logits.f32"))
        for rep in (2, 3):
            name = f"c294-{case}-{rep}-on.native"
            target = json.loads(read(C294, name + "/result.json"))
            require(
                target["case"] == case
                and target["profile"] == "R0"
                and target["mode"] == 0
                and target["initial_prefix_mode"] == 0
                and target["official_input_ids"] == ids
                and target["teacher_forced_ids"] == cont
                and target["trace"] is True,
                "target identity",
            )
            relative = Path(C294) / "raw" / name / "events.tsv"
            groups, publications = read_arm(
                raw_root / relative, manifest["results/" + str(relative)]
            )
            loads = sum(
                minimum(groups[lid::36], 40, initial=[128 * lid + e for e in kept])
                for lid, kept in enumerate(selections)
            )
            r0_logits = digest(read(C294, name + "/all33.logits.f32"))
            argsame = [
                x == y
                for x, y in zip(
                    original["native_argmax_ids"], target["native_argmax_ids"], strict=True
                )
            ]
            require(len(argsame) == 33, "wrong output positions")
            arms[name] = {
                "source": source,
                "source_initial_sha256": digest(snapshot),
                "source_selection_sha256": digest(encoded(selections)),
                "positive_score_layers": sum(any(row["route_hotness"]) for row in layer_rows),
                "zero_score_selected": sum(
                    row["route_hotness"][e] == 0
                    for row, sel in zip(layer_rows, selections, strict=True)
                    for e in sel
                ),
                "never_reserved_in_source_selected": sum(
                    not row["seen"][e]
                    for row, sel in zip(layer_rows, selections, strict=True)
                    for e in sel
                ),
                "top40_absent_source_residents": sum(
                    len(set(sel) - set(row["slot_expert"]))
                    for row, sel in zip(layer_rows, selections, strict=True)
                ),
                "cross_profile_full33_sha256": {"source_E": e_logits, "target_R0": r0_logits},
                "cross_profile_full33_equal": e_logits == r0_logits,
                "cross_profile_argmax_matches": sum(argsame),
                "observed_r0_publications": publications,
                "min_loads_free_placement": loads,
                "min_payload_bytes": loads * EXPERT_BYTES,
                "wire_ceiling_steps_s": STEPS * LINK_BPS / (8 * loads * EXPERT_BYTES),
                "decision": "NO_GO_TRANSFERRED_TOP40"
                if loads > MAX_LOADS
                else "GO_COST_SCREEN_ONLY",
            }
    return {
        "evidence": "CONDITIONAL_FORMAL_CROSS_PROFILE",
        "maximum_loads_for_six": MAX_LOADS,
        "rule_sha256": RULE_PIN,
        "clock_sha256": CLOCK_PIN,
        "source_manifest_sha256": PINS,
        "fixture_sha256": INPUT_PIN,
        "arms": arms,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--historical-results", required=True, type=Path)
    ap.add_argument("--source-backend", required=True, type=Path)
    ap.add_argument("--new-output-dir", required=True, type=Path)
    a = ap.parse_args()
    a.new_output_dir.mkdir(exist_ok=False)
    try:
        receipt = audit(a.historical_results, a.source_backend)
    except Exception as e:
        (a.new_output_dir / "FAIL.txt").write_text(type(e).__name__ + "\n")
        raise
    tmp = a.new_output_dir / ".receipt.pending"
    tmp.write_text(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n")
    tmp.rename(a.new_output_dir / "receipt.json")


if __name__ == "__main__":
    main()
