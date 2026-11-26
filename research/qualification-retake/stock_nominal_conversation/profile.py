"""Run one bounded, uninstrumented stock-derived E20 conversation under C55/C118."""

import hashlib
import json
import math
import os
import re
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from stock_prefault_ready import start as lazy  # noqa: E402

core, full = lazy.core, lazy.full
DATE = "2026-10-05"
KWARGS = '{"tesy_template_date":"2026-10-05"}'
FAMILY = "9b82832754bacc7e9944e4ca77c65396c9e855bc216adf96bbd8743b8d960f32"
B20 = "4e7055d10ebc748164326d03dec6e7659a4d26bdf9b4e28b16483d58c8e25120"
INPUT = "c3e0b72ecaa2e13ac6871af6cef5ef05d6ba1b5b7f76cf685177ce83f121b92c"
END = datetime(2026, 11, 25, 5, 34, tzinfo=UTC)
MAX_SECONDS = 650


def geometry(log):
    marks = full.geometry(log)
    examples = re.findall(r"init: chat template, example_format: '(.*?)'\r?\n", log, re.S)
    marks["dated_init_example"] = len(examples) == 1 and re.findall(
        r"^Current date: ([^\r\n]+)$", examples[0], re.M
    ) == [DATE]
    return marks


def date_arguments(args, command_prefix):
    args = list(args)
    core.check(args.count("--chat-template-kwargs") == 1, "template_argument_count")
    index = args.index("--chat-template-kwargs") + 1
    core.check(args[index] == full.KWARGS, "unexpected_prior_template_arguments")
    args[index] = KWARGS
    command = [*command_prefix, *args]
    return args, hashlib.sha256(b"\0".join(map(os.fsencode, command))).hexdigest()


def original_receipt(path, pin):
    # Timestamp only orders these local publications against the first C55 sample.
    with path.open("rb") as stream:
        before = core.stable(os.fstat(stream.fileno()))
        data = stream.read(65537)
        core.check(
            len(data) <= 65536
            and hashlib.sha256(data).hexdigest() == pin
            and before == core.stable(os.fstat(stream.fileno())) == core.identity(path),
            "original_gate_identity",
        )
    return json.loads(data), before[3]


def validate_gates(a, window_start):
    family, fam_mtime = original_receipt(a.family_receipt, FAMILY)
    nominal, input_mtime = original_receipt(a.input_receipt, INPUT)
    prior = lazy.sealed_json(HERE.parent / "stock_server_logits/physical-r2/receipt.json", B20)
    core.check(
        family["status"] == "PASS_E10_AND_E20_TRANSFER_BITWISE"
        and [x["arm"] for x in family["arms"]] == ["S", "A", "B", "B20"]
        and all(x["bitwise_equal"] for x in family["arms"])
        and family["arms"][-1]["receipt_sha256"] == B20
        and prior["status"] == "PASS_STOCK_SERVER_RAW_LOGITS_ARM"
        and prior["arm"] == "B20"
        and prior["child_gone"]
        and prior["returncode"] == 0
        and nominal["status"] == "PASS_TWO_NOMINAL_INPUTS_RENDER_AND_OFFICIAL_IDS"
        and nominal["template_date"] == DATE
        and nominal["original_jinja_sha256"] == full.ORIGINAL
        and nominal["stock_jinja_sha256"] == full.ADAPTED,
        "product_prerequisites",
    )
    first = datetime.fromisoformat(window_start)
    core.check(
        first.tzinfo is not None and first.timestamp() * 1e9 > max(fam_mtime, input_mtime),
        "C55_precedes_publication_of_prior_results",
    )
    return {
        "family_sha256": FAMILY,
        "physical_B20_sha256": B20,
        "nominal_input_sha256": INPUT,
        "original_family_mtime_ns": fam_mtime,
        "original_nominal_mtime_ns": input_mtime,
        "first_C55_utc": first.isoformat(),
    }


def uninstrumented(pid, library_path):
    # Read only the environment of this newly launched server. Return no environment values.
    base = Path("/proc") / str(pid)
    check_environment((base / "environ").read_bytes(), (base / "maps").read_text(), library_path)


def check_environment(environ, maps, library_path):
    values = dict(v.split(b"=", 1) for v in environ.split(b"\0") if v)
    maps = maps.splitlines()
    named = [f[5] for line in maps if len(f := line.split(maxsplit=5)) == 6]
    core.check(
        values.get(b"TESY_STOCK_LAZY_MMAP") == b"1"
        and values.get(b"LD_LIBRARY_PATH") == os.fsencode(library_path)
        and not any(k in values for k in (b"LD_PRELOAD", b"LD_AUDIT"))
        and not any(k.startswith(b"TESY_F32_") for k in values)
        and all(Path(path.removesuffix(" (deleted)")).name != "observer.so" for path in named),
        "observer_mapped_or_unexpected_loader_environment",
    )


class Experiment(lazy.Experiment):
    def require_window(self, seconds):
        # The reused supervisor reserves C118, READY and shutdown. Add the after-READY window.
        required = seconds + (self.profile.probe.timeout_s if seconds else 0)
        remaining = min(
            MAX_SECONDS - (time.monotonic() - self.profile.start_clock),
            (END - datetime.now(UTC)).total_seconds(),
        )
        core.check(remaining > required, "product_unit_clock_or_cutoff")

    def raw_size(self):
        return sum(f.stat().st_size for f in self.raw.rglob("*") if f.is_file())

    def watch(self):
        super().watch()
        if product := self.profile.progress.get("product_progress"):
            product = product.copy()
            turn, phase = product.get("turn"), product.get("phase")
            if phase == "chat" and turn in (1, 2):
                deadline = product.get("deadline_monotonic_s")
                sent = product.get("send_monotonic_s")
                if deadline is not None and sent is not None:
                    core.check(
                        math.isfinite(deadline)
                        and math.isfinite(sent)
                        and 0 < deadline - sent <= (180 if turn == 1 else 90) + 0.001,
                        "invalid_client_phase_deadline",
                    )
                    core.check(time.monotonic() < deadline, f"T{turn}_REQUEST_TIMEOUT")


class Profile(full.Profile):
    unit = HERE
    geometry = staticmethod(geometry)

    def __init__(self, probe_factory):
        super().__init__(probe_factory)
        core.check(
            probe_factory.ram_profile == "R0_E20"
            and probe_factory.protocol_path == HERE / "protocol.md"
            and probe_factory.run_id == "stock-nominal-e20-c281"
            and probe_factory.pass_status == "PASS_STOCK_TWO_NATURAL_REQUESTS_LOCAL_HISTORY"
            and probe_factory.timeout_s == 300,
            "unqualified_product_probe",
        )
        self.ram_profile = "R0_E20"
        self.paging_cap_bytes = 20 * core.GIB
        self.start_clock = time.monotonic()
        self.probe_factory = probe_factory

    @staticmethod
    def add_arguments(parser):
        lazy.Profile.add_arguments(parser)
        for name in ("family-receipt", "input-receipt", "history"):
            parser.add_argument("--" + name, type=Path, required=True)

    def prepare(self, a, raw, r):
        args = super().prepare(a, raw, r)
        with (a.policy.parent / "samples.jsonl").open() as samples:
            first = json.loads(samples.readline())["utc"]
        r["prerequisites"] = validate_gates(a, first)
        args, argv_sha = date_arguments(
            args, [str(a.binary.resolve()), "-m", str(core.MODEL), *core.ARGS, "-lv", "4"]
        )
        self.probe = self.probe_factory(a.history)
        r.update(
            template_kwargs=json.loads(KWARGS),
            argv_sha256=argv_sha,
            product_supervisor_sha256=core.sha(__file__),
            client_sha256=core.sha(HERE / "client.py"),
            scope="STOCK_E20_TWO_NATURAL_C281_TURNS",
            elapsed_budget_s=MAX_SECONDS,
        )
        return args

    def runtime_overlay(self, a, exe, stock, mount, env, r):
        previous = lazy.Profile.runtime_overlay(self, a, exe, stock, mount, env, r)
        core.check(
            env["TESY_STOCK_LAZY_MMAP"] == "1"
            and "LD_PRELOAD" not in env
            and not any(x.startswith("TESY_F32_") for x in env),
            "product_loader_environment",
        )
        self.library_path = env["LD_LIBRARY_PATH"]
        r.update(
            scope="STOCK_E20_TWO_NATURAL_C281_TURNS",
            experiment_deadline_utc=END.isoformat(),
            observer_requested=False,
        )
        self.record = r
        run = Experiment(
            previous.root,
            previous.image,
            previous.digest,
            previous.stat,
            previous.device,
            previous.raw,
            r,
        )
        run.profile = self
        return run

    def at_ready(self, pid, raw, cancelled, missing_placement):
        if not missing_placement:
            uninstrumented(pid, self.library_path)
            self.record["ready_no_logits_observer"] = True
        return super().at_ready(pid, raw, cancelled, missing_placement)

    def close(self, record):
        first_reason = record.get("reason")
        super().close(record)
        if first_reason and record.get("reason") != first_reason:
            record["additional_cleanup_reason"] = record.get("reason")
            record["reason"] = first_reason
        product = self.progress.get("product_progress")
        if isinstance(product, dict):
            # The client maintains this public diagnostic apart from the private chat exchange.
            record["product_progress"] = product.copy()
            if record["status"] != self.pass_status:
                turn, stage = product.get("turn"), product.get("phase")
                finished = product.get("completed_turns", 0)
                sent = product.get("send_monotonic_s")
                censored = stage == "chat" and turn in (1, 2) and type(sent) in (int, float)
                record["interrupted_product"] = {
                    "phase": stage,
                    "turn": turn,
                    "completed_turns": finished,
                    "open_exchange_without_completion": censored,
                    "elapsed_since_open_request_s": round(max(0, time.monotonic() - sent), 4)
                    if censored
                    else None,
                    "next_turn_not_run": 2 if turn == 1 else None,
                }


def main():
    from stock_nominal_conversation.client import Probe

    # Include preflight, C118 and cleanup in the process budget. During a live server
    # the existing 50-ms watcher also stops its own process group on this boundary.
    profile = Profile(Probe)
    if not {"--help", "-h"}.intersection(sys.argv):
        delay = min(MAX_SECONDS, (END - datetime.now(UTC)).total_seconds())
        core.check(delay > 0, "unit_expired")

        def expire(_signum, _frame):
            raise TimeoutError("product_supervisor_650s_or_absolute_cutoff")

        signal.signal(signal.SIGALRM, expire)
        signal.setitimer(signal.ITIMER_REAL, delay)
    try:
        core.cli(paging=True, placement_log=True, ready_profile=profile)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == "__main__":
    main()
