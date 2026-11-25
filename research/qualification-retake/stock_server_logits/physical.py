"""Qualify one complete first-prompt logit row in a controlled stock HTTP server."""

import argparse
import hashlib
import http.client
import json
import os
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from aster_split import probe as split  # noqa: E402
from stock_prefault_ready import start as lazy  # noqa: E402
from stock_server_logits import inputs  # noqa: E402

core = lazy.core
ARMS = ("S", "A", "B", "B20")
PASS = "PASS_STOCK_SERVER_RAW_LOGITS_ARM"
END = datetime(2026, 11, 25, 5, 15, tzinfo=UTC)
ARM = b"tesy-first-prompt16-v1\n"
CALLER = "7cf9543328e80642d8c5d2212b1926fa5dc66f551d3d1e4cf04ab7900622c5e3"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def select_environment(env, arm, stock_dir, image, stock_sha, candidate_sha):
    core.check(arm in ARMS, "unknown_arm")
    if arm == "S":
        env.pop("TESY_STOCK_LAZY_MMAP", None)
        env["LD_LIBRARY_PATH"] = str(stock_dir)
        return (stock_dir / lazy.SONAME).resolve(strict=True), stock_sha
    env["TESY_STOCK_LAZY_MMAP"] = "0" if arm == "A" else "1"
    env["LD_LIBRARY_PATH"] = str(image.parent) + ":" + str(stock_dir)
    return image, candidate_sha


def validate_observer(receipt, observer):
    pin = (HERE / "observer.sha256").read_text().strip()
    r = lazy.sealed_json(receipt, pin)
    sources = ("capture.cpp", "fixture.py", "test_fixture.py")
    core.check(
        r["status"] == "PASS_SYNTHETIC_SERVER_LOGIT_OBSERVER"
        and r["sources_sha256"] == {n: core.sha(HERE / n) for n in sources}
        and r["program_sha256"] == r["sources_sha256"]["fixture.py"]
        and r["model_forwards"] == 0
        and r["gpu_used"] is False
        and r["observer_sha256"] == core.sha(observer),
        "synthetic_observer_gate",
    )
    return r, pin


def arm_once(directory):
    core.check(not list(directory.iterdir()), "capture_directory_already_used")
    pending = directory / "ARM.pending"
    split.save(pending, ARM)
    os.link(pending, directory / "ARM")
    pending.unlink()


class Probe:
    protocol_path = HERE / "physical-protocol.md"
    timeout_s = 90
    pass_status = PASS

    def __init__(self, arm):
        self.run_id = "stock-server-logits-" + arm.lower()

    def run(self, pid, raw, cancelled, progress):
        log = (raw / "server.log").read_text(errors="replace")
        ports = set(re.findall(r"listening on http://127\.0\.0\.1:(\d+)\b", log))
        core.check(len(ports) == 1 and not cancelled.is_set(), "server_identity_or_cancelled")
        port = int(ports.pop())
        split.owned_listener(pid, port)
        body = split.json_bytes(
            dict(
                prompt=self.ids,
                n_predict=1,
                id_slot=0,
                cache_prompt=True,
                temperature=0,
                seed=42,
                stream=False,
                return_tokens=True,
                n_probs=0,
            )
        )
        split.save(raw / "request.json", body)
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=self.timeout_s)
        tick = time.monotonic()
        try:
            arm_once(raw / "capture")
            core.check(not cancelled.is_set(), "cancelled_before_request")
            progress.update(http_requests_sent=1, sampling_tokens_requested=1)
            connection.request("POST", "/completion", body, {"Content-Type": "application/json"})
            response = connection.getresponse()
            payload = response.read(256 * 1024 + 1)
            elapsed = time.monotonic() - tick
            split.save(raw / "response.json", payload)
            core.check(
                response.status == 200 and elapsed <= self.timeout_s and len(payload) <= 256 * 1024,
                "request_failed_or_budget",
            )
            data = split.strict_json(payload)
            counts = split.validated_counts(data, 16, 0)
            settings = data["generation_settings"]
            core.check(
                settings["temperature"] == 0 and settings["n_probs"] == 0,
                "effective_sampling_parameters",
            )
            return {
                **counts,
                "http_status": response.status,
                "request_sha256": digest(body),
                "response_sha256": digest(payload),
                "sampled_id": data["tokens"][0],
                "client_s": elapsed,
                "owned_server_pid": pid,
            }
        finally:
            connection.close()


def prior_rows(family, arm, expected, first_start):
    from stock_server_logits.compare import verified_row

    past = []
    baseline = None
    for previous in ARMS[: ARMS.index(arm)]:
        reports, private = family / (previous + ".report"), family / (previous + ".private")
        record, row = verified_row(reports, private)
        core.check(
            record["arm"] == previous
            and record["prior_receipts_sha256"] == past
            and all(record.get(k) == v for k, v in expected.items()),
            "previous_arm_different_family_or_configuration",
        )
        if baseline is None:
            baseline, first_start = row, datetime.fromisoformat(record["family_started_utc"])
        core.check(
            record["family_started_utc"] == first_start.isoformat() and row == baseline,
            "previous_arm_logit_mismatch_or_clock",
        )
        past.append(core.sha(reports / "receipt.json"))
    return past, first_start, baseline


def collect_capture(raw, record, baseline):
    from stock_server_logits.compare import summarize

    folder = raw / "capture"
    core.check(
        {p.name for p in folder.iterdir()} == {"ARM", "row.f32", "capture.json"}
        and all(p.is_file() and not p.is_symlink() for p in folder.iterdir())
        and (folder / "ARM").read_bytes() == ARM,
        "capture_files_or_arm",
    )
    for name in ("capture.json", "row.f32"):
        target = raw / name
        core.check(not target.exists() and not target.is_symlink(), "capture_overwrite")
        (folder / name).rename(target)
    c = core.read(raw / "capture.json")
    core.check(
        (raw / "row.f32").stat().st_size == 804352
        and (raw / "capture.json").stat().st_size <= 65536,
        "capture_output_size",
    )
    row = (raw / "row.f32").read_bytes()
    ex = record["after_ready"]
    core.check(len(row) == 804352, "capture_row_size")
    comparison = summarize(row if baseline is None else baseline, row)
    record.update(
        row_file="row.f32",
        row_sha256=digest(row),
        greedy_id=comparison["candidate_argmax"],
        sampled_id=ex["sampled_id"],
        request_sha256=ex["request_sha256"],
        response_sha256=ex["response_sha256"],
        comparison=comparison,
        capture_sha256=core.sha(raw / "capture.json"),
        arm_marker_sha256=digest(ARM),
    )
    core.check(
        c["status"] == "PASS"
        and c["reason"] == ""
        and c["profile"] == "stock120b"
        and type(c["prearm_calls"]) is int
        and c["prearm_calls"] >= 0
        and c["armed_calls"] == 1
        and c["row_index"] == 15
        and c["n_vocab"] == 201088
        and c["row_bytes"] == len(row)
        and c["row_sha256"] == record["row_sha256"]
        and c["caller_offset"] in (0x26951F, 0x269A6D)
        and c["caller_sha256"] == CALLER
        and c["provider_sha256"] == record["active_libllama_sha256"]
        and c["argmax"] == record["greedy_id"] == record["sampled_id"]
        and ex["cache_n"] == 0
        and ex["prompt_n"] == 16
        and ex["predicted_n"] == 1
        and record["http_requests_sent"] == record["sampling_tokens_requested"] == 1,
        "post_exit_capture_or_sampler",
    )
    core.check(
        comparison["finite_candidate"] is True and comparison["bitwise_equal"],
        "nonfinite_or_gold_row_mismatch",
    )


class Experiment(lazy.Experiment):
    def bind(self, refs, dep_ids):
        self.original = dep_ids[lazy.SONAME]
        self.chosen = core.Reference(refs, self.image, self.digest)
        self.candidate = self.chosen.key
        core.check(self.candidate != self.original, "overlay_same_inode")
        if self.arm != "S":
            dep_ids[lazy.SONAME] = self.candidate
        self.observer_ref = core.Reference(refs, self.observer, self.observer_sha)

    def mapping(self, live):
        self.verify_candidate_stat()
        core.check(
            core.stable(os.fstat(self.observer_ref.file.fileno()))
            == self.observer_ref.identity
            == core.identity(self.observer),
            "observer_changed_since_authentication",
        )
        return {
            "active_libllama_present": (self.original if self.arm == "S" else self.candidate)
            in live,
            "other_libllama_absent": (self.candidate if self.arm == "S" else self.original)
            not in live,
            "observer_present": self.observer_ref.key in live,
        }

    def require_window(self, seconds):
        # The existing READY admission reserves 60+180+10 or 180+10. Add the single request.
        required = seconds + (90 if seconds else 0)
        core.check(
            (self.deadline - datetime.now(UTC)).total_seconds() > required, "physical_family_clock"
        )

    def raw_size(self):
        return sum(p.stat().st_size for p in self.raw.rglob("*") if p.is_file())

    def finish(self, record):
        folder = self.raw / "capture"
        record["private_capture_sha256"] = {
            p.name: core.sha(p)
            for p in sorted(folder.iterdir())
            if p.is_file() and not p.is_symlink() and p.stat().st_size <= 804352
        }
        super().finish(record)
        if record["status"] == PASS:
            core.check(record["child_gone"] and record["returncode"] == 0, "child_not_collected")
            collect_capture(self.raw, record, self.baseline)
            self.require_window(0)


class Profile(lazy.full.Profile):
    unit = HERE

    def __init__(self, arm):
        super().__init__(Probe(arm))
        self.arm = arm
        self.started = datetime.now(UTC)
        if arm == "B20":
            self.ram_profile = "R0_E20"
            self.paging_cap_bytes = 20 * core.GIB

    @staticmethod
    def add_arguments(parser):
        lazy.Profile.add_arguments(parser)
        for key in ("family-dir", "observer", "observer-receipt", "c110-raw"):
            parser.add_argument("--" + key, type=Path, required=True)

    def prepare(self, a, raw, r):
        args = super().prepare(a, raw, r)
        family = a.family_dir.resolve(strict=True)
        core.check(
            family.is_dir()
            and family.stat().st_uid == os.geteuid()
            and family.stat().st_mode & 0o777 == 0o700,
            "family_directory_must_be_private",
        )
        self.probe.ids, meta = inputs.load_prompt(a.c110_raw)
        self.baseline = None
        self.observer = a.observer.resolve(strict=True)
        proof, pin = validate_observer(a.observer_receipt, self.observer)
        window = core.read(a.policy.parent / "receipt.json")
        rows = [
            json.loads(line)
            for line in (a.policy.parent / "samples.jsonl").read_text().splitlines()
        ]
        lazy.fresh_c55(rows, proof, window)
        r.update(
            arm=self.arm,
            protocol_sha256=core.sha(self.probe.protocol_path),
            physical_entry_sha256=core.sha(__file__),
            observer_receipt_sha256=pin,
            observer_sha256=proof["observer_sha256"],
            **meta,
        )
        r["scope"] = "FULL_SWA_C110_FIRST_16_SINGLE_GREEDY_TOKEN"
        common = {
            k: r[k]
            for k in (
                "measurement_commit",
                "measurement_tree",
                "prompt_ids_sha256",
                "observer_sha256",
                "observer_receipt_sha256",
                "protocol_sha256",
                "C55_receipt_sha256",
            )
        }
        prior = []
        start = self.started
        if not a.before_inventory_only:
            core.check(
                a.new_raw.resolve() == family / (self.arm + ".private")
                and a.new_output.resolve() == family / (self.arm + ".report"),
                "arm_output_layout",
            )
            prior, start, self.baseline = prior_rows(family, self.arm, common, start)
        self.deadline = min(END, start + timedelta(minutes=30))
        r.update(
            prior_receipts_sha256=prior,
            family_started_utc=start.isoformat(),
            family_deadline_utc=self.deadline.isoformat(),
        )
        (raw / "capture").mkdir(mode=0o700)
        return args

    def runtime_overlay(self, a, exe, stock, mount, env, r):
        # Authenticate the same stock build, rebuilt gold, candidate, CPU gate and model namespace.
        predecessor = lazy.Profile.runtime_overlay(self, a, exe, stock, mount, env, r)
        active, active_sha = select_environment(
            env,
            self.arm,
            exe.parent,
            predecessor.image,
            r["stock_libllama_sha256"],
            predecessor.digest,
        )
        env.update(
            LD_PRELOAD=str(self.observer),
            TESY_F32_PROFILE="stock120b",
            TESY_F32_PROVIDER_SHA256=active_sha,
            TESY_F32_DIR=str((predecessor.raw / "capture").resolve()),
        )
        r.update(
            scope="FULL_SWA_C110_FIRST_16_SINGLE_GREEDY_TOKEN",
            loader_sha256=lazy.check_loader(exe, active, stock["own_libs_sha256"], env),
            lazy_mmap=env.get("TESY_STOCK_LAZY_MMAP"),
            active_libllama_sha256=active_sha,
            experiment_deadline_utc=self.deadline.isoformat(),
        )
        result = Experiment(
            predecessor.root,
            predecessor.image,
            predecessor.digest,
            predecessor.stat,
            predecessor.device,
            predecessor.raw,
            r,
        )
        result.arm, result.deadline, result.baseline = self.arm, self.deadline, self.baseline
        result.observer, result.observer_sha = self.observer, r["observer_sha256"]
        return result


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--arm", choices=ARMS, required=True)
    if "--help" in sys.argv or "-h" in sys.argv:
        parser.print_help()
        core.cli(paging=True, placement_log=True, ready_profile=Profile("S"))
    args, rest = parser.parse_known_args()
    sys.argv[1:] = rest
    core.cli(paging=True, placement_log=True, ready_profile=Profile(args.arm))


if __name__ == "__main__":
    main()
