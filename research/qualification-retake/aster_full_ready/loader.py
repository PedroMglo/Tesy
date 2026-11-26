"""Start the pinned stock E10 server with full SWA and the date-bound Aster template."""

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "stock_startup"))
import start  # noqa: E402

ORIGINAL = "a4c9919cbbd4acdd51ccffe22da049264b1b73e59055fa58811a99efbd7c8146"
ADAPTED = "0ccef2b31697ba30f891ed18cfc1203b8603f26fc4233faa98839c674819b9eb"
BUILD = "089ff4f67b7914f075e67293c08a195a23af9cc2df49d3848815674f3f33bb52"
PLACEMENT = "50a35a1e5c3fde78066d1378e13dfeb89867d9970528135ff3294c6aa5bd1bf7"
KWARGS = '{"tesy_template_date":"2026-09-29"}'
TEMPLATE = "aster-date.jinja"


def fixed_template(original):
    expression = b'strftime_now("%Y-%m-%d")'
    start.check(hashlib.sha256(original).hexdigest() == ORIGINAL, "unknown_original_jinja")
    start.check(original.count(expression) == 1, "ambiguous_template_clock")
    adapted = original.replace(expression, b"tesy_template_date")
    start.check(hashlib.sha256(adapted).hexdigest() == ADAPTED, "incorrect_adapted_jinja")
    return adapted


def geometry(log):
    marks = start.logged_geometry(log)
    # The server reports its dynamically assigned port just after model loaded.
    ports = re.findall(r"listening on http://127\.0\.0\.1:(\d+)\b", log)
    marks["ready"] = marks["ready"] and len(ports) == 1 and 0 < int(ports[0]) <= 65535
    # Match exact inventories, independent of whitespace in the upstream format strings.
    flags = re.I
    for key, pattern, expected in (
        ("full_kv", r"creating non-SWA KV cache, size = (\d+) cells", ["8192"]),
        ("swa_kv", r"creating\s+SWA KV cache, size = (\d+) cells", ["8192"]),
        ("gpu_kv_mib", r"CUDA0 KV buffer size =\s+([\d.]+) MiB", ["288.00", "288.00"]),
        ("slot", r"initializing, n_slots = (\d+), n_ctx_slot = (\d+)", [("1", "8192")]),
        (
            "cuda",
            r"CUDA0 MoE cache size =\s+([\d.]+) MiB for [\d.]+ MiB of host experts, "
            r"(\d+)% of the misses on the CPU",
            [("2042.30", "0")],
        ),
        ("group", r"(\d+) layers,\s*mxfp4:\s+(\d+) slots", [("36", "161")]),
    ):
        marks[key] = re.findall(pattern, log, flags) == expected
    marks["full_swa_mode"] = log.count("using full-size SWA cache") == 1
    examples = re.findall(r"init: chat template, example_format: '(.*?)'\r?\n", log, re.S)
    marks["dated_init_example"] = len(examples) == 1 and re.findall(
        r"^Current date: ([^\r\n]+)$", examples[0], re.M
    ) == ["2026-09-29"]
    return marks


class Profile:
    unit = HERE
    geometry = staticmethod(geometry)

    def __init__(self, probe=None):
        self.probe = probe
        # Only the explicitly selected probe class may change the startup-only E10 recipe.
        self.ram_profile = vars(type(probe)).get("ram_profile", "E10")
        start.check(self.ram_profile in ("E10", "R0_E20"), "unknown_stock_ram_profile")
        self.paging_cap_bytes = (20 if self.ram_profile == "R0_E20" else 10) * start.GIB
        self.run_id = probe.run_id if probe else "stock-aster-full-ready"
        self.pass_status = probe.pass_status if probe else "PASS_STOCK_FULL_SWA_ASTER_READY_ONLY"
        self.thread = None
        self.result = None
        self.failure = None
        self.progress = {"http_requests_sent": 0, "sampling_tokens_requested": 0}
        if probe is not None:
            start.check(
                self.run_id != "stock-aster-full-ready"
                and re.fullmatch(r"[a-z0-9-]+", self.run_id)
                and self.pass_status.startswith("PASS_")
                and math.isfinite(probe.timeout_s)
                and probe.timeout_s > 0,
                "unbounded_or_unnamed_probe",
            )

    @property
    def probe_started(self):
        return self.thread is not None

    def admit_memory(self, window, policy):
        memories = (policy["memory"], window["memory"], window["canonical_memory"])
        start.check(
            min(m["cap_max_bytes"] for m in memories) >= self.paging_cap_bytes,
            "C55_insufficient_stock_ram_cap",
        )
        if self.ram_profile == "R0_E20":
            start.check(
                window["status"] == "PASS_RESOURCE_WINDOW_ONLY"
                and not window["reason"]
                and all(
                    m["reserve_bytes"] >= 2 * start.GIB
                    and m["available_min_bytes"] >= self.paging_cap_bytes + m["reserve_bytes"]
                    for m in memories
                ),
                "C55_E20_host_reserve_or_window",
            )

    def prepare(self, a, raw, record):
        a.new_raw.chmod(0o700)
        raw.chmod(0o700)

        def git(*args):
            return subprocess.check_output(["git", "-C", ROOT, *args], text=True).strip()

        head, tree = git("rev-parse", "HEAD", "HEAD^{tree}").splitlines()
        start.check(head == a.expect_head and not git("status", "--porcelain"), "unfrozen_checkout")
        start.check(
            start.sha(a.build_receipt) == BUILD and start.sha(a.placement) == PLACEMENT,
            "unknown_stock_or_placement_receipt",
        )
        wpath = a.policy.parent / "receipt.json"
        window, policy = start.read(wpath), start.read(a.policy)
        c55 = HERE.parent / "nvme_admission"
        start.check(
            window["protocol_sha256"] == start.sha(c55 / "protocolo.md")
            and window["runner_sha256"] == start.sha(c55 / "window.py")
            and window["canonical_policy_sha256"] == start.sha(a.policy)
            and window["status"] in ("PASS_RESOURCE_WINDOW_ONLY", "NOT_ADMITTED")
            and not set(window["reason"])
            - {"C55_CAP_UNAVAILABLE", "HOST_CAP_PLUS_RESERVE_UNAVAILABLE"}
            and tuple(window["selected_stat"]) == start.identity(start.MODEL),
            "C55_window_or_model_stat",
        )
        self.admit_memory(window, policy)
        if self.ram_profile == "R0_E20":
            record.update(
                stock_ram_profile=self.ram_profile,
                host_reserve_bytes=policy["memory"]["reserve_bytes"],
                ram_profile_sha256=start.sha(HERE.parent / "aster_ram_budget/profile.md"),
            )
        # A later C55 is reproducible under the same collection procedure and live C118.
        start.check(
            start.sha(wpath.parent / "samples.jsonl") == window["window_sha256"],
            "changed_C55_samples",
        )
        with (raw / TEMPLATE).open("xb") as f:
            f.write(fixed_template(a.original_jinja.read_bytes()))
        (raw / TEMPLATE).chmod(0o400)
        self.verify_template(raw)
        args = [
            "--swa-full",
            "--jinja",
            "--chat-template-file",
            str((raw / TEMPLATE).resolve()),
            "--chat-template-kwargs",
            KWARGS,
        ]
        command = [str(a.binary.resolve()), "-m", str(start.MODEL), *start.ARGS, "-lv", "4", *args]
        record.update(
            scope="FULL_SWA_ASTER_READY"
            if self.probe is None
            else "FULL_SWA_ASTER_READY_WITH_PROBE",
            measurement_commit=head,
            measurement_tree=tree,
            source_sha256=start.sha(__file__),
            C55_receipt_sha256=start.sha(wpath),
            original_jinja_sha256=ORIGINAL,
            effective_jinja_sha256=ADAPTED,
            template_kwargs=json.loads(KWARGS),
            argv_sha256=hashlib.sha256(b"\0".join(map(os.fsencode, command))).hexdigest(),
        )
        if self.probe:
            record.pop("sampling_forwards_requested")  # Counts belong to the supplied probe.
            record.update(
                after_ready_protocol_sha256=start.sha(self.probe.protocol_path),
                after_ready_timeout_s=self.probe.timeout_s,
            )
        return args

    def verify_template(self, raw):
        start.check(start.sha(raw / TEMPLATE) == ADAPTED, "template_changed_after_preparation")

    def at_ready(self, pid, raw, cancelled, missing_placement):
        self.verify_template(raw)
        if self.probe is None or missing_placement:
            return None
        deadline = time.monotonic() + self.probe.timeout_s
        self.launch_probe(pid, raw, cancelled)
        return deadline

    def launch_probe(self, pid, raw, cancelled):
        start.check(not self.probe_started and not cancelled.is_set(), "invalid_probe_start")

        def worker():
            try:
                self.result = self.probe.run(pid, raw, cancelled, self.progress)
                start.check(isinstance(self.result, dict), "probe_returned_no_receipt")
            except Exception as exc:
                self.failure = str(exc) or type(exc).__name__

        self.thread = threading.Thread(target=worker, name="tesy-ready-probe", daemon=True)
        self.thread.start()

    def probe_finished(self, record):
        if self.thread.is_alive():
            return False
        start.check(self.failure is None, self.failure or "probe_failure")
        record["after_ready"] = self.result
        return True

    def close(self, record):
        if self.probe_started:
            self.thread.join(timeout=2)
            if self.thread.is_alive():
                record.update(status="FAIL", reason="probe_did_not_stop")
        if self.probe is not None:
            # Requests, sampled tokens and internal target forwards have different scopes.
            record.pop("sampling_forwards_requested", None)
            record["http_requests_sent"] = self.progress["http_requests_sent"]
            record["sampling_tokens_requested"] = self.progress["sampling_tokens_requested"]


def cli_for(probe=None):
    start.cli(paging=True, placement_log=True, ready_profile=Profile(probe))


if __name__ == "__main__":
    cli_for()
