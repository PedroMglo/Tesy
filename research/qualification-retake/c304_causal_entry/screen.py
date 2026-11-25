"""Seal historical prefix choices or evaluate already-sealed choices in a new process."""

import argparse
import hashlib
import json
import resource
import subprocess
from pathlib import Path

from selection import HERE, MANIFEST, NAMES, UNIT, require, select_arms

COVERAGE = "570df50a9434bc8b77cf8b083fc151f7a14068ec2d0b682ed03625a5c79a24c8"
RELOAD = "fc90aaf7164613218ec51e678f568b8359c116f42517952c6d2540b10b5fd5bd"
SCENARIO = "824f66278bbc5caa20b70da1b960341412a8518f29866a921cb252f0c30d5e81"
STUDY = UNIT.parents[1] / "results/c304-prefix-cost-observer-repair-20261007"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pinned(path, want):
    data = path.read_bytes()
    require(sha(data) == want, "wrong source: " + path.name)
    return data


def git(*args):
    return subprocess.check_output(
        ["git", "-c", "core.preloadIndex=false", "-c", "index.threads=1", *args],
        cwd=HERE,
        text=True,
    ).strip()


def publish(directory, name, result):
    tmp = directory / (".pending-" + name)
    body = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    with tmp.open("xb") as f:
        f.write(body)
    tmp.rename(directory / name)
    return sha(body)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", choices=("select", "evaluate"), required=True)
    ap.add_argument("--raw-dir", type=Path, required=True)
    ap.add_argument("--new-output-dir", type=Path, required=True)
    ap.add_argument("--sealed-selection", type=Path)
    ap.add_argument("--selection-sha256")
    a = ap.parse_args()
    required_inputs = bool(a.sealed_selection and a.selection_sha256)
    if (
        a.phase == "evaluate"
        and not required_inputs
        or a.phase == "select"
        and (a.sealed_selection or a.selection_sha256)
    ):
        ap.error("evaluate alone needs --sealed-selection AND --selection-sha256")
    require(not a.new_output_dir.resolve().is_relative_to(a.raw_dir.resolve()), "protect raw")
    a.new_output_dir.mkdir(mode=0o700)
    report = {"status": "FAIL_PRESERVED", "phase": a.phase}
    try:
        for key, cap in (
            (resource.RLIMIT_CPU, 120),
            (resource.RLIMIT_AS, 512 << 20),
            (resource.RLIMIT_FSIZE, 8 << 20),
        ):
            soft, hard = resource.getrlimit(key)
            resource.setrlimit(key, (min(x for x in (soft, hard, cap) if x >= 0), hard))
        require(not git("status", "--porcelain"), "dirty measurement tree")
        head, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
        pinned(HERE / "protocol.md", COVERAGE)
        pinned(HERE / "reload-protocol.md", RELOAD)
        report.update(
            commit=head,
            tree=tree,
            coverage_protocol_sha256=COVERAGE,
            reload_protocol_sha256=RELOAD,
            manifest_sha256=MANIFEST,
            selector_sha256=sha((HERE / "selection.py").read_bytes()),
            driver_sha256=sha(Path(__file__).read_bytes()),
        )
        if a.phase == "select":
            members = select_arms(a.raw_dir, STUDY)
            sealed = dict(
                commit=head,
                tree=tree,
                selector_sha256=report["selector_sha256"],
                reload_protocol_sha256=RELOAD,
                manifest_sha256=MANIFEST,
                arms=members,
            )
            report.update(
                selection_sha256=publish(a.new_output_dir, "selection.json", sealed),
                status="PASS_SEALED_BEFORE_DECODE",
                route_rule="NOT_RUN_MISSING_TILE_MEMBERSHIP",
                coverage_decision="INCONCLUSIVE",
                ids_per_arm={
                    k: {field: len(v[field]) for field in ("reload_twice", "reload_last")}
                    for k, v in members.items()
                },
            )
        else:
            sealed = json.loads(pinned(a.sealed_selection, a.selection_sha256))
            require(
                sealed["commit"] == head
                and sealed["tree"] == tree
                and sealed["selector_sha256"] == report["selector_sha256"]
                and sealed["manifest_sha256"] == MANIFEST
                and sealed["reload_protocol_sha256"] == RELOAD
                and set(sealed["arms"]) == set(NAMES),
                "incompatible selection",
            )
            # Only this phase may import the decoder or read historical outcomes.
            from evaluate import evaluate_arm

            historical = json.loads(pinned(STUDY / "heldout-scenario.json", SCENARIO))["cases"]
            report.update(
                arms={},
                selection_sha256=a.selection_sha256,
                evaluator_sha256=sha((HERE / "evaluate.py").read_bytes()),
                scenario_sha256=SCENARIO,
            )
            for name in NAMES:
                case = "heldout-" + name.split("-")[2]
                report["arms"][name] = evaluate_arm(
                    a.raw_dir, name, sealed["arms"][name], historical[case]
                )
            report["paired_controls"] = {}
            for i in (0, 2):
                left, right = (report["arms"][name] for name in NAMES[i : i + 2])
                matches = {
                    field: left[field] == right[field]
                    for field in (
                        "P_sha256",
                        "I_sha256",
                        "F_sha256",
                        "ordered_rank_sha256",
                        "ordered_greedy_ids_sha256",
                    )
                }
                require(
                    all(
                        matches[field]
                        for field in (
                            "P_sha256",
                            "I_sha256",
                            "ordered_rank_sha256",
                            "ordered_greedy_ids_sha256",
                        )
                    ),
                    "historical trajectories differ",
                )
                report["paired_controls"][NAMES[i].split("-")[2]] = matches
            report["decisions"] = {}
            for scale in ("1", "0.8"):
                reach = {
                    name: arm["scopes"]["reload_twice"]["scales"][scale]["reaches"]
                    for name, arm in report["arms"].items()
                }
                greedy = [v for name, v in reach.items() if name.endswith("greedy")]
                report["decisions"][scale] = dict(
                    reaches=reach,
                    greedy_control_gate="GO_PAID_CAUSAL_FIXTURE_ONLY"
                    if all(greedy)
                    else "NO_GO_IN_FAILING_CASES",
                )
            report["status"] = "PASS_RELOAD_UNIVERSE_SCREEN"
    except FileNotFoundError as exc:
        report.update(status="NOT_RUN_RAW_REQUIRED", error=Path(exc.filename).name)
    except (
        OSError,
        KeyError,
        ValueError,
        ArithmeticError,
        AssertionError,
        MemoryError,
        subprocess.CalledProcessError,
    ) as exc:
        report.update(error=str(exc) or type(exc).__name__)
    publish(a.new_output_dir, "receipt.json", report)
    print(report["status"])
    return int("error" in report)


if __name__ == "__main__":
    raise SystemExit(main())
