"""Replay one causal filter and price the target verification groups observed on the laptop."""

import argparse
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
AUDIT = run_path(str(HERE / "review_family.py"))
R, H, G, need, sha, save = (AUDIT[k] for k in ("R", "H", "G", "need", "sha", "save"))
METHOD = "8be79dcd49b589347997008566c7741033a97a18e88eda3dd0423e999dc49c29"
REVIEW = "aa1f06224bfa702e79d5c351b94b11a51c2978436b37780cf021e880cf07f1df"
PILOT = R["FAMILY"]


def proposal(history, room, filter_context):
    cur = len(history) - 1
    if cur <= 5 or room <= 0:
        return ()
    pattern = history[-2:]
    for j in range(cur - 3, 0, -1):
        if history[j : j + 2] != pattern:
            continue
        if cur - j - 2 < 2 or (filter_context and history[j - 1] != history[-3]):
            return ()
        return history[j + 2 : j + 4][:room]
    return ()


def controls():
    good = (9, 6, 2, 3, 7, 8, 0, 6, 2, 3)
    bad = good[:-3] + (5, 2, 3)
    recent = (9, 6, 2, 3, 1, 2, 0, 4, 2, 3, 7, 8, 0, 6, 2, 3)
    tests = {
        "agree": proposal(good, 2, True) == (7, 8),
        "disagree": proposal(bad, 2, True) == () and proposal(bad, 2, False) == (7, 8),
        "most_recent": proposal(recent, 2, True) == () and proposal(recent, 2, False) == (7, 8),
        "short": proposal(good[:5], 2, True) == (),
        "cap": proposal(good, 0, True) == () and proposal(good, 1, True) == (7,),
    }
    need(all(tests.values()), "causal context controls")
    return tests


def replay(case, filter_context):
    history = tuple(case["prompt"]) + tuple(case["target"][:1])
    target = case["target"]
    at = 1
    blocks = []
    while at < len(target):
        room = max(0, min(8192 - len(history) + 1 - 2, case["cap"] - at - 1))
        baseline = H["F"]["RULE"]["draft"](history, 2, 2)[:room]
        need(proposal(history, room, False) == baseline, "pinned N2/M2 rule")
        pair = proposal(history, room, filter_context)
        accepted = 0
        while (
            accepted < len(pair)
            and at + accepted < len(target)
            and pair[accepted] == target[at + accepted]
        ):
            accepted += 1
        emitted = min(len(target) - at, accepted + 1)
        blocks.append((at, pair, accepted, emitted))
        history += tuple(target[at : at + emitted])
        at += emitted
    need(history == tuple(case["prompt"]) + tuple(target), "all target IDs")
    return blocks


def price(actions, original, on, off, cut, metrics, *, nominal):
    known_positions = {entry for entry in original if entry[1]}
    full = early = 0
    missing = []
    for entry in actions:
        at, pair, accepted, count = entry
        end = at + count - 1
        if not pair:
            marks = off
        elif entry in known_positions:
            marks = on
        else:
            missing.append(
                dict(
                    at=at,
                    accepted=accepted,
                    emitted=count,
                    before_final=(None if cut is None else at <= cut),
                )
            )
            continue
        full += marks[end] - marks[at - 1]
        if cut is not None and at <= cut:
            early += marks[min(end, cut)] - marks[at - 1]
    favorable = metrics["decode_s"] + (full - (off[-1] - off[0])) / 1e6
    final = None if cut is None else metrics["first_final_s"] + (early - (off[cut] - off[0])) / 1e6
    return dict(
        unpriced=missing,
        conditional_zero_unpriced_decode_s=favorable,
        available_new_cost_or_residency_change_to_equal_off_s=metrics["decode_s"] - favorable,
        available_new_cost_or_residency_change_to_six_s=metrics["predicted"] / 6 - favorable
        if nominal
        else None,
        conditional_zero_unpriced_first_final_s=final,
        available_before_final_to_equal_off_s=None
        if final is None
        else metrics["first_final_s"] - final,
        available_before_final_to_ten_s=None if not nominal or final is None else 10 - final,
        conditional_prefill_s_to_ten_with_free_unpriced=None
        if not nominal or final is None
        else metrics["prefill_s"] + 10 - final,
    )


def study(a):
    head, tree = G["tree"](G["REPO"])
    need(head == a.commit and sha(HERE / "context-protocol.md") == METHOD, "sealed replay")
    f = R["reopen"](a.family, AUDIT["FAMILY"])
    p = R["reopen"](a.pilot, PILOT)
    official = G["read"](a.review / "result.json", REVIEW)
    need(
        f["status"] == official["status"] == "GO_FOUR_NATURAL_DIAGNOSTICS"
        and p["model_starts"] == 1
        and p["started_requests"] == 2,
        "source families",
    )
    pilot = G["read"](a.pilot_review / "receipt.json", R["SERVER"]["REPORT_FIXTURE"])
    data, steps = R["cases"](a)
    results = {}
    for i, label in enumerate(("T1", "T2"), 1):
        case = data[label]
        original = replay(case, False)
        need(
            original
            == [(s["at"], tuple(s["proposal"]), s["accepted"], s["emitted"]) for s in steps[label]],
            "complete native schedule",
        )
        candidate = replay(case, True)
        off, cut = AUDIT["ticks"](a.family / "OFF", i)
        metrics = official["arms"]["OFF"]["rows"][i - 1]
        population = {}
        for key, actions in (("fixed", original), ("filtered", candidate)):
            blocks = [v for v in actions if v[1]]
            population[key] = dict(
                serial=len(actions) - len(blocks),
                blocks=len(blocks),
                proposed=sum(len(v[1]) for v in blocks),
                accepted=sum(v[2] for v in blocks),
                confirmed=1 + sum(v[3] for v in actions),
                depths=[sum(v[2] == j for v in blocks) for j in range(3)],
            )
        trial = {}
        for name, root, proof in (
            ("first_ON", a.pilot, pilot["recomputed"]),
            ("second_ON", a.family, official["arms"]["ON"]),
        ):
            on, oncut = AUDIT["ticks"](root / "ON", i)
            need(
                len(off) == len(on) == len(case["target"])
                and cut == oncut
                and proof["trajectories"][str(i)]["accepted"] == population["fixed"]["accepted"],
                "identical target sequence and text cut",
            )
            trial[name] = price(candidate, original, on, off, cut, metrics, nominal=i == 2)
        results[label] = dict(
            population=population,
            pricing=trial,
            first_final_sample=None if cut is None else cut + 1,
            serial_first_final_s=metrics["first_final_s"],
            serial_decode_s=metrics["decode_s"],
            serial_rate=metrics["decode_tok_s"],
        )
    return dict(
        status="TRACE_DERIVED_CONDITIONAL_PRICES",
        commit=head,
        tree=tree,
        protocol_sha256=METHOD,
        family_sha256=AUDIT["FAMILY"],
        pilot_sha256=PILOT,
        four_arm_review_sha256=REVIEW,
        controls=controls(),
        turns=results,
        new_model_starts=0,
        new_requests=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "family",
        "pilot",
        "review",
        "pilot-review",
        "capture",
        "verified",
        "plan",
        "new-output-dir",
    ):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    save(a.new_output_dir / "result.json", study(a))
