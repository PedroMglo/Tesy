"""Supervise one independent E10 Aster reference from C55 through exit."""

import json
import os
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from stock_prefault_ready import start as shared  # noqa: E402

core, full = shared.core, shared.full
END = datetime(2026, 11, 25, 6, 20, tzinfo=UTC)
C55_PIN = "4f87414f2660f8afe25ae619c04239d2cb8b4f1c0a331d7114af24e17229a9c0"
PROTOCOL_UTC = datetime(2026, 11, 25, 5, 19, 31, tzinfo=UTC)
MAX_SECONDS = 3300
READ_LIMIT = 5 << 40
RAW_LIMIT = 64 << 20


def stock_maps(environ, maps, stock_dir):
    env = dict(x.split(b"=", 1) for x in environ.split(b"\0") if x)
    libraries = set()
    for line in maps.splitlines():
        parts = line.split(maxsplit=5)
        if len(parts) != 6:
            continue
        name = Path(parts[-1].removesuffix(" (deleted)")).name
        core.check(name != "observer.so", "observer_mapped")
        if name.startswith("libllama.so"):
            libraries.add(parts[-1])
    core.check(
        env.get(b"LD_LIBRARY_PATH") == os.fsencode(stock_dir)
        and not any(k in env for k in (b"TESY_STOCK_LAZY_MMAP", b"LD_PRELOAD", b"LD_AUDIT"))
        and not any(k.startswith(b"TESY_F32_") for k in env)
        and libraries == {str((stock_dir / shared.SONAME).resolve(strict=True))},
        "unexpected_stock_provider_or_interposition",
    )


def check_window(window, policy, rows, now):
    first, last = (datetime.fromisoformat(rows[i]["utc"]) for i in (0, -1))
    core.check(
        first.date() == END.date()
        and first.tzinfo is not None
        and PROTOCOL_UTC < first < last <= now <= END
        and len(rows) == window["samples"]
        and (last - first).total_seconds() >= 60
        and window["span_s"] >= 60,
        "new_C55_window",
    )
    for memory in (window["memory"], window["canonical_memory"], policy["memory"]):
        core.check(
            memory["reserve_bytes"] >= 2 * core.GIB
            and memory["available_min_bytes"] >= memory["reserve_bytes"] + 10 * core.GIB
            and memory["cap_max_bytes"] >= 10 * core.GIB,
            "E10_host_reserve",
        )
    return first.isoformat(), last.isoformat()


class Experiment:
    def __init__(self, profile, stat, device, raw, record):
        self.profile = profile
        self.stat = stat
        self.device = device
        self.private = raw.parent
        self.record = record

    def bind(self, refs, dep_ids):
        self.stock_key = dep_ids[shared.SONAME]

    def mapping(self, live):
        return {"original_stock_libllama_present": self.stock_key in live}

    def require_window(self, seconds):
        remain = min(
            MAX_SECONDS - (time.monotonic() - self.profile.started),
            (END - datetime.now(UTC)).total_seconds(),
        )
        core.check(remain > (seconds + 3000 if seconds else 0), "fixed_reference_unit_cutoff")

    def before_spawn(self):
        self.require_window(190)
        self.start_bytes = shared.bytes_read(self.stat)
        self.record["model_device_read_start_bytes"] = self.start_bytes

    def amounts(self):
        delta = shared.bytes_read(self.stat) - self.start_bytes
        size = sum(f.stat().st_size for f in self.private.rglob("*") if f.is_file())
        return delta, size

    def enforce(self, delta, size):
        core.check(0 <= delta < READ_LIMIT, "NVME_namespace_reset_or_5TiB")
        core.check(size <= RAW_LIMIT, "raw_64MiB")
        self.require_window(0)

    def watch(self):
        self.enforce(*self.amounts())

    def finish(self, record):
        delta, size = self.amounts()
        scope = record["io_stat_delta_by_device"].get(self.device, {})
        record.update(
            raw_size_bytes=size,
            model_device_physical_read_delta_bytes=delta,
            model_device_cgroup_rbytes=scope.get("rbytes"),
        )
        core.check(isinstance(scope.get("rbytes"), int), "model_device_cgroup_read_accounting")
        self.enforce(delta, size)


class Profile(full.Profile):
    unit = HERE

    def __init__(self, probe_factory):
        super().__init__(probe_factory)
        core.check(
            probe_factory.ram_profile == self.ram_profile == "E10"
            and self.paging_cap_bytes == 10 * core.GIB
            and probe_factory.run_id == "stock-aster-fixed-natural-reference"
            and probe_factory.timeout_s == 3000
            and probe_factory.protocol_path == HERE / "protocol.md"
            and probe_factory.pass_status == "PASS_FIXED_ASTER_NATURAL_ENVELOPE",
            "unexpected_fixed_reference_probe",
        )
        self.probe_factory = probe_factory
        self.started = time.monotonic()

    @staticmethod
    def add_arguments(parser):
        parser.add_argument("--historical-results", type=Path, required=True)
        parser.add_argument("--c55-sha256", choices=[C55_PIN], default=C55_PIN)

    def prepare(self, a, raw, r):
        self.probe = self.probe_factory(a.historical_results)
        args = super().prepare(a, raw, r)
        window = shared.sealed_json(a.policy.parent / "receipt.json", a.c55_sha256)
        rows = [json.loads(s) for s in (a.policy.parent / "samples.jsonl").read_text().splitlines()]
        self.window = window
        first, last = check_window(window, core.read(a.policy), rows, datetime.now(UTC))
        r.update(
            scope="INDEPENDENT_STOCK_E10_C133_T2_FIXED_HISTORY",
            supervisor_sha256=core.sha(__file__),
            client_sha256=core.sha(HERE / "client.py"),
            experiment_deadline_utc=END.isoformat(),
            process_budget_s=MAX_SECONDS,
            first_C55_utc=first,
            last_C55_utc=last,
            C133_T2_individual_timeout_s=600,
            original_product_window_continues_for_content=True,
            model_device_read_cap_bytes=READ_LIMIT,
            private_raw_cap_bytes=RAW_LIMIT,
        )
        return args

    def runtime_overlay(self, a, exe, stock, mount, env, r):
        # The base supervisor authenticates each stock inode. This hook only
        # verifies loader resolution and adds guards. It does not alter env or dep_ids.
        stock_dir = exe.parent
        core.check(
            env["LD_LIBRARY_PATH"] == str(stock_dir)
            and not any(k in env for k in ("LD_PRELOAD", "LD_AUDIT", "TESY_STOCK_LAZY_MMAP"))
            and not any(k.startswith("TESY_F32_") for k in env)
            and len(stock["own_libs_sha256"]) == 8,
            "stock_environment_or_libraries",
        )
        self.stock_dir = stock_dir
        self.record = r
        r["loader_sha256"] = shared.check_loader(
            exe, (stock_dir / shared.SONAME).resolve(strict=True), stock["own_libs_sha256"], env
        )
        source = self.window["model_device"]
        core.check(source == mount["source"] and mount["fstype"] == "btrfs", "model_mount_changed")
        stat, device = shared.nvme_counter(source)
        shared.bytes_read(stat)
        r.update(
            model_device_major_minor=device,
            stock_libllama_sha256=stock["own_libs_sha256"][shared.SONAME],
        )
        return Experiment(self, stat, device, a.new_raw / "raw", r)

    def at_ready(self, pid, raw, cancelled, missing_placement):
        if not missing_placement:
            proc = Path("/proc") / str(pid)
            stock_maps((proc / "environ").read_bytes(), (proc / "maps").read_text(), self.stock_dir)
            self.record["ready_original_stock_without_observer"] = True
        return super().at_ready(pid, raw, cancelled, missing_placement)

    def close(self, record):
        original_reason = record.get("reason")
        super().close(record)
        if original_reason and record.get("reason") != original_reason:
            record["cleanup_reason"] = record.get("reason")
            record["reason"] = original_reason
        if progress := self.progress.get("product_progress"):
            record["product_progress"] = progress.copy()


def main():
    from aster_fixed_reference.client import Probe

    profile = Profile(Probe)
    if not {"--help", "-h"}.intersection(sys.argv):
        delay = min(MAX_SECONDS, (END - datetime.now(UTC)).total_seconds())
        core.check(delay > 0, "unit_expired")

        def expire(_signum, _frame):
            raise TimeoutError("fixed_reference_process_budget_or_cutoff")

        signal.signal(signal.SIGALRM, expire)
        signal.setitimer(signal.ITIMER_REAL, delay)
    try:
        core.cli(paging=True, placement_log=True, ready_profile=profile)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == "__main__":
    main()
