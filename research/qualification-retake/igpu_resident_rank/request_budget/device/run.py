"""Prepare or run a single authenticated C281 P with an observer outside its service cgroup."""

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
FAMILY = HERE.parents[2] / "packed_nvme_manifest/server_profile/conversation"
sys.path.insert(0, str(HERE))
import grade  # noqa: E402
import probe  # noqa: E402

HISTORICAL_FAMILY = "9428a171c354c6cd2d3f12ecb338249ac33be9ced2633ab8c4fdddbdd2b3e284"
PROTOCOL = "534c7fb922b741b32deb717e02e75ba2c08f56ba"
STATIC = "PASS_PREPARED_SINGLE_P_DEVICE_MONITOR"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pinned(path, expected):
    data = path.read_bytes()
    probe.need(hashlib.sha256(data).hexdigest() == expected, "changed " + path.name)
    return json.loads(data)


def git(*args):
    return subprocess.check_output(["git", "-C", str(REPO), *args])


def source_identity(a):
    probe.need(
        git("rev-parse", "HEAD").decode().strip() == a.commit
        and not git(
            "-c", "core.preloadIndex=false", "-c", "index.threads=1", "status", "--porcelain"
        )
        and re.fullmatch(r"tesy-c281-nvme-[a-z0-9-]+", a.unit_prefix),
        "unclean checkout, commit or unit",
    )
    fixed = git("show", f"{PROTOCOL}:{(HERE / 'protocol.md').relative_to(REPO)}")
    probe.need(fixed == (HERE / "protocol.md").read_bytes(), "prospective protocol")
    hist = pinned(a.source_family, HISTORICAL_FAMILY)
    ident = hist["identity"]
    probe.need(hist["status"] == "PASS_C281_TRANSPORT_BLOCK" and hist["order"] == "POR", "history")
    inputs = dict(ident["inputs"], repo=str(REPO), window=str(a.window.resolve(strict=True)))
    local = {
        p.name: digest(p)
        for p in (HERE / "protocol.md", HERE / "run.py", HERE / "grade.py", HERE / "probe.py")
    }
    inherited = {k: digest(FAMILY / k) for k in ("family.py", "transport_profile.py", "review.py")}
    probe.need(inherited == ident["supervisor"], "historical arm producer and validators")
    c55 = pinned(a.window / "receipt.json", a.window_sha256)
    probe.need(
        c55["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and c55["canonical_memory"]["cap_max_bytes"] >= 20 * 2**30,
        "C55 E20",
    )
    derived = pinned(
        Path(inputs["derived_dir"]) / "receipt.json",
        "cd4c0665c5485268cddfc7dba576b1cf490222c120cf34f72d555a6cbccbc5b9",
    )
    topology = probe.topology(Path(derived["model_path"]), Path(derived["pack_path"]))
    return dict(
        commit=a.commit,
        tree=git("rev-parse", "HEAD^{tree}").decode().strip(),
        source_sha256=local,
        arm_sources_sha256=inherited,
        history_sha256=HISTORICAL_FAMILY,
        inputs=inputs,
        c55_sha256=a.window_sha256,
        c270=ident["c270"],
        preflight_sha256=ident["c269_preflight"],
        unit=a.unit_prefix + "-p",
        topology=topology,
    )


def invoke(selected, out, execute):
    arm_dir = out / "P"
    args = [sys.executable, "-IB", str(FAMILY / "family.py")]
    for key, value in selected["inputs"].items():
        args.extend(["--" + key.replace("_", "-"), value])
    args.extend(
        [
            "--commit",
            selected["commit"],
            "--unit-prefix",
            selected["unit"].removesuffix("-p"),
            "--preflight-sha256",
            selected["preflight_sha256"],
            "--window-sha256",
            selected["c55_sha256"],
            "--c270-sha256",
            selected["c270"],
            "--new-output-dir",
            str(arm_dir),
            "--arm",
            "P",
        ]
    )
    if execute:
        args.append("--execute")
    with (out / "P.log").open("xb") as log:
        with subprocess.Popen(
            args, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
        ) as child:
            try:
                code = child.wait(timeout=650)
            except (KeyboardInterrupt, subprocess.TimeoutExpired):
                child.send_signal(signal.SIGINT)
                try:
                    child.wait(timeout=35)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
                raise
    path = arm_dir / "arm.json"
    arm = json.loads(path.read_bytes()) if path.is_file() else {}
    probe.need(
        code == 0
        and arm.get("mode") == "P"
        and arm.get("status") == ("PASS_ONE_NATURAL_ARM" if execute else "PREPARED_ONLY"),
        "original P failed; inspect P.log and P/arm.json",
    )
    return digest(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for field in ("source-family", "window", "new-output-dir"):
        ap.add_argument("--" + field, type=Path, required=True)
    for field in ("commit", "unit-prefix", "window-sha256"):
        ap.add_argument("--" + field, required=True)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--prepared", type=Path)
    ap.add_argument("--prepared-sha256")
    a = ap.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    receipt = {"status": "FAIL_PRESERVED"}
    try:
        sel = source_identity(a)
        receipt["identity"] = sel
        if not a.execute:
            probe.need(a.prepared is None and a.prepared_sha256 is None, "unexpected preparation")
            sample = out / "self-samples.tsv"
            control = probe.record(
                probe.identity(os.getpid()), sel["topology"], sample, threading.Event(), limit=6
            )
            probe.need(control["samples"] == 6, "unprivileged monitor check")
            receipt.update(
                self_probe=control,
                self_probe_sha256=digest(sample),
                arm_sha256=invoke(sel, out, False),
                status=STATIC,
            )
        else:
            probe.need(
                a.prepared is not None and a.prepared_sha256, "preparation receipt and SHA required"
            )
            prior = pinned(a.prepared, a.prepared_sha256)
            probe.need(
                prior["status"] == STATIC
                and prior["identity"] == sel
                and digest(a.prepared.parent / "P/arm.json") == prior["arm_sha256"]
                and digest(a.prepared.parent / "self-samples.tsv") == prior["self_probe_sha256"],
                "sealed P preparation",
            )
            receipt["prepared_sha256"] = a.prepared_sha256
            stop = threading.Event()
            observations = {}
            path = out / "samples.tsv"
            launch = out / "P/raw" / (sel["unit"] + ".launch.json")
            worker = threading.Thread(
                target=probe.physical_observer,
                args=(launch, sel["unit"], sel["topology"], path, stop, observations),
            )
            worker.start()
            try:
                receipt["arm_sha256"] = invoke(sel, out, True)
            finally:
                stop.set()
                worker.join()
                receipt["observation"] = observations
                if path.is_file():
                    receipt["trace_sha256"] = digest(path)
            probe.need(observations.get("status") == "OBSERVED", "observer failed; original P kept")
            native = json.loads((out / "P/receipt.json").read_bytes())
            probe.need(
                native["runtime_authority"]["native_pid"]
                == observations["inventory"]["process_identity"]["pid"],
                "observer/arm PID",
            )
            result = grade.grade_arm(out / "P", path, observations["inventory"])
            receipt.update(grade=result, status=result["status"])
    except Exception as exc:
        receipt["reason"] = f"{type(exc).__name__}: {exc}"
    probe.save(out / "receipt.json", receipt)
    print(receipt["status"], receipt.get("reason", ""))
    return int(receipt["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
