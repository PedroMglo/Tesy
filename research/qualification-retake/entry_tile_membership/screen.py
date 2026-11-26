"""Separate the pre-decode tile selection on C294 from its historical timing screen."""

import argparse
import hashlib
import json
import resource
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parent
sys.path[:0] = [str(UNIT), str(UNIT / "primary_entry_timing")]
from primary_entry_timing import screen as entry  # noqa: E402
from warm_routes40 import boundary as live  # noqa: E402
from warm_routes40 import witness  # noqa: E402

backing = entry.backing
require = backing.require
PROTOCOL = "7c07caea8be36ceb7042b0ebc8f71db275b889cfe51ff130c9f8fde5239bd90e"


def geometry(case):
    length = backing.PROMPT[case]
    sizes = [256] * 7 + [length - 153 - 7 * 256, 153]
    plans = []
    start = 0
    for call, size in enumerate(sizes, 1):
        for ub, offset in enumerate(range(0, size, 32), 1):
            plans.append((call, ub, tuple(range(start + offset, start + min(offset + 32, size)))))
        start += size
    return sizes, plans


def bytes_to_cut(sizes, ubatches):
    # WRT1 signature, C/D per call, U/E per graph, positions, one O per call,
    # R headers for 35 regular layers per graph and one final layer per call, and top-four rows.
    calls, positions = len(sizes), sum(sizes)
    return (
        4
        + 6 * calls
        + 3 * ubatches
        + 2 * positions
        + 2 * calls
        + 5 * (35 * ubatches + calls)
        + 4 * (35 * positions + calls)
    )


def decode_prefix(stream, case):
    sizes, plan = geometry(case)
    raw = stream.read(bytes_to_cut(sizes, len(plan)))
    require(raw[-1:] == b"D", "the measured prefix did not end at call return")
    # F terminates only this parser invocation. No routing or position record is synthesized.
    graphs, rows = witness.read(raw + b"F")
    require(graphs == plan, "uncertain physical tile boundary")
    return [(ub, layer, position, ids) for call, ub, layer, position, ids in rows if call == 9]


def choose(rows, residents):
    masks = {}
    for ub, layer, _, ids in rows:
        require(1 <= ub <= 5 and 0 <= layer < 36 and len(set(ids)) == len(ids) == 4, "tile row")
        if layer == 35:
            require(ub == 5, "unexpected final layer observation")
            continue
        for e in ids:
            require(type(e) is int and 0 <= e < 128, "expert")
            key = (layer, e)
            masks[key] = masks.get(key, 0) | (1 << (ub - 1))
    generous = [
        (layer, e)
        for (layer, e), mask in sorted(masks.items())
        if mask & 16 and e not in residents[layer]
    ]
    main = []
    for key in generous:
        mask = masks[key]
        if any(not mask & (1 << gap) and mask & ((1 << gap) - 1) for gap in range(1, 4)):
            main.append(key)
    return {
        "last_tile": [[*k, masks[k]] for k in generous],
        "reappeared": [[*k, masks[k]] for k in main],
    }


def select(family):
    p = entry.warm.p
    arms = p.family_inputs(family, p.FAMILY_SHA)
    cases = {}
    for case in ("nominal153", "code153"):
        modes = {}
        for arm in (a for a in arms if a["case"] == case):
            path = family / arm["native_dir"]
            h = arm["native_sha256"]
            wrt = path / "routed-witness.bin"
            with wrt.open("rb") as f:
                require(hashlib.file_digest(f, "sha256").hexdigest() == h[wrt.name], "WRT1 anchor")
                f.seek(0)
                rows = decode_prefix(f, case)
            snap = path / "boundary-i.json"
            doc = json.loads(backing.pinned(snap, h[snap.name]))
            digest = live.verify(case, snap)["slot_vector_sha256"]
            require(digest == arm["I_sha256"], "I witness")
            residents = [{e for e, _, s, _ in layer if s == 2} for layer in doc["slot_vector"]]
            picked = choose(rows, residents)
            require(len(rows) == 35 * 153 + 1, "increment route count")
            modes[arm["mode"]] = dict(I_sha256=digest, sets=picked, wrt_sha256=h[wrt.name])
        require(modes["ON"] == modes["OFF"], "WRT1 ON/OFF drift")
        cases[case] = modes["OFF"]
    return cases


def project(groups, choices, fixed):
    tiers = {}
    for name in ("CPU", "CUDA"):

        def belongs(layer, tier=name):
            return (layer < 25) == (tier == "CPU")

        ready = {(layer, e) for layer, e in choices if belongs(layer)}
        layer_groups = [(layer, r) for layer, r in groups if belongs(layer)]
        mandatory = {(layer, e) for layer, r in layer_groups for e in r}
        old = sum(max(r.values(), default=0) for _, r in layer_groups)
        new = sum(
            max((u for e, u in r.items() if (layer, e) not in ready), default=0)
            for layer, r in layer_groups
        )
        tiers[name] = dict(
            selected=len(ready),
            legal_first_misses_removed=len(mandatory & ready),
            selected_never_demanded=len(ready - mandatory),
            base_read_us=old,
            remaining_us=new,
        )
    rem = sum(v["remaining_us"] for v in tiers.values())
    return dict(
        tiers=tiers,
        required_read_us=rem,
        max_read_scale=(16_000_000 - 3 * fixed) / (3 * rem) if rem else None,
        scales={label: backing.score(rem, fixed, n, d) for label, n, d in entry.SCALES},
    )


def evaluate(raw, cases):
    reference = json.loads(
        backing.pinned(UNIT / "primary_backing/evidence/receipt.json", entry.BOUND)
    )
    backing.pinned(Path(backing.__file__), reference["source_sha256"])
    backing.pinned(Path(backing.c295.__file__), backing.critical.C295)
    paid, orig, components = [
        json.loads(backing.pinned(UNIT / path, h))["arms"] for path, h in backing.PINS.items()
    ]
    arms = {}
    for name, anchor in reference["arms"].items():
        case = name.split("-")[1]
        control = backing.arm(raw, name, paid[name + ".native"], orig[name], components[name])
        require(
            control == anchor and control["original_fixed_us"] == control["charged_fixed_us"],
            "control/overlap",
        )
        residents, facts = backing.boundary.audit_arm(raw, name)
        selected = cases[case]
        require(
            facts["boundary_slot_vector_sha256"] == selected["I_sha256"] == anchor["anchor_sha256"],
            "I",
        )
        journal = raw / (name + ".native") / "events.tsv"
        rows = backing.c295.events(journal, True)
        backing.pinned(journal, anchor["raw_sha256"]["events.tsv"])
        groups, _, _ = entry.collect(rows, residents)
        fixed = anchor["charged_fixed_us"]
        v = {}
        for key, items in {"empty": [], **selected["sets"]}.items():
            choices = {(layer, e) for layer, e, _ in items}
            require(
                len(choices) == len(items)
                and all(e not in residents[layer] for layer, e in choices),
                "choices already in I",
            )
            v[key] = project(groups, choices, fixed)
        require(
            sum(len(r) for _, r in groups) == anchor["total"]["required"]
            and v["empty"]["required_read_us"] == anchor["total"]["required_read_floor_us"],
            "empty control",
        )
        require(
            v["empty"]["required_read_us"]
            >= v["reappeared"]["required_read_us"]
            >= v["last_tile"]["required_read_us"],
            "nested universes",
        )
        arms[name] = dict(
            fixed_us=fixed,
            native_decode_us=anchor["native_us"],
            raw_sha256=anchor["raw_sha256"],
            scopes=v,
        )
    return arms


def publish(out, name, report):
    tmp = out / (".pending-" + name)
    body = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    with tmp.open("xb") as f:
        f.write(body)
    tmp.rename(out / name)
    return hashlib.sha256(body).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", choices=("select", "evaluate"), required=True)
    ap.add_argument("--family", type=Path)
    ap.add_argument("--raw-dir", type=Path)
    ap.add_argument("--sealed-selection", type=Path)
    ap.add_argument("--selection-sha256")
    ap.add_argument("--new-output-dir", required=True, type=Path)
    a = ap.parse_args()
    if (
        a.phase == "select"
        and (not a.family or a.raw_dir or a.sealed_selection or a.selection_sha256)
    ) or (
        a.phase == "evaluate"
        and (a.family or not a.raw_dir or not a.sealed_selection or not a.selection_sha256)
    ):
        ap.error("select: --family. evaluate: --raw-dir, --sealed-selection, --selection-sha256")
    require(
        not a.new_output_dir.resolve().is_relative_to((a.family or a.raw_dir).resolve()),
        "protect raw",
    )
    a.new_output_dir.mkdir(mode=0o700)
    r = dict(status="FAIL_PRESERVED", phase=a.phase)
    try:
        for key, cap in (
            (resource.RLIMIT_CPU, 120),
            (resource.RLIMIT_AS, 512 * 2**20),
            (resource.RLIMIT_FSIZE, 8 * 2**20),
        ):
            soft, hard = resource.getrlimit(key)
            resource.setrlimit(key, (min(x for x in (cap, soft, hard) if x >= 0), hard))
        git = entry.warm.p.git
        require(
            not git(
                HERE,
                "-c",
                "core.preloadIndex=false",
                "-c",
                "index.threads=1",
                "status",
                "--porcelain",
            ),
            "dirty tree",
        )
        backing.pinned(HERE / "protocol.md", PROTOCOL)
        commit = git(HERE, "rev-parse", "HEAD")
        tree = git(HERE, "rev-parse", "HEAD^{tree}")
        r.update(
            commit=commit,
            tree=tree,
            protocol_sha256=PROTOCOL,
            program_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        )
        if a.phase == "select":
            sets = select(a.family)
            sha = publish(
                a.new_output_dir,
                "selection.json",
                dict(
                    commit=commit,
                    tree=tree,
                    protocol_sha256=PROTOCOL,
                    family_sha256=entry.warm.p.FAMILY_SHA,
                    cases=sets,
                ),
            )
            r.update(status="PASS_SEALED_WRT_TILE_SELECTION", selection_sha256=sha)
        else:
            choice = json.loads(backing.pinned(a.sealed_selection, a.selection_sha256))
            require(
                choice["commit"] == commit
                and choice["tree"] == tree
                and choice["protocol_sha256"] == PROTOCOL
                and choice["family_sha256"] == entry.warm.p.FAMILY_SHA,
                "incompatible selection",
            )
            arms = evaluate(a.raw_dir, choice["cases"])
            r.update(
                status="PASS_DEVELOPMENT_TILE_SCREEN",
                selection_sha256=a.selection_sha256,
                primary_backing_receipt_sha256=entry.BOUND,
                arms=arms,
            )
    except FileNotFoundError as exc:
        r.update(status="NOT_RUN_RAW_REQUIRED", error=Path(exc.filename).name)
    except (
        ValueError,
        IndexError,
        KeyError,
        MemoryError,
        OSError,
        subprocess.CalledProcessError,
    ) as exc:
        r.update(error=str(exc) or type(exc).__name__)
    publish(a.new_output_dir, "receipt.json", r)
    print(r["status"])
    return int("error" in r)


if __name__ == "__main__":
    raise SystemExit(main())
