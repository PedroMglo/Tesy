"""Explore one lazy-mmap E20 startup under the existing stock READY supervisor."""

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from aster_full_ready import loader as full  # noqa: E402

core = full.start
RESIDENT = HERE.parent / "stock_prefault_resident"
OVERLAY = "5f58a70ddc141a7a874776429c61e37169a9d7694e8b54e44e23aec0f9c69e02"
LOGITS = "aabc5c6e701c0df890d1fa21c9b590dcd4bf8a29f56390c1beb3f169848d1290"
TINY_GGUF = "31a310d53e5c4c2a22994fc2fa75f095446af380885948120306fd6e7213a08d"
SONAME = "libllama.so.0"
IMAGE = "libllama.so.0.9.0"
READ_LIMIT = 1 << 40
END = datetime(2026, 11, 25, 4, 52, tzinfo=UTC)


def sealed_json(path, expected):
    data = path.read_bytes()
    core.check(
        re.fullmatch(r"[0-9a-f]{64}", expected) and hashlib.sha256(data).hexdigest() == expected,
        "receipt_sha256",
    )
    return json.loads(data)


def check_attribution(r, build):
    core.check(
        r["status"] == "PASS_TINY_CPU_INFERENCE_AND_MMAP"
        and r["clean"] is True
        and r["commit"] == "9f4e1641e648c3ae2c8294946af7b29ddf3a5dbc"
        and r["repair_protocol_sha256"] == core.sha(RESIDENT / "attribution-repair.md")
        and r["stock_pin"] == core.PIN
        and r["build_receipt_sha256"] == OVERLAY
        and r["gguf_sha256"] == TINY_GGUF
        and r["protocol_sha256"] == core.sha(RESIDENT / "attribution-protocol.md")
        and r["resident_runner_sha256"] == core.sha(RESIDENT / "runner.py")
        and r["upstream_fixture_sha256"]
        == core.sha(HERE.parent / "stock_prefault_build/tiny_fixture.py")
        and r["program_sha256"] == core.sha(RESIDENT / "attribution.py")
        and r["memory_max_bytes"] == 768 << 20
        and r["swap_max_bytes"] == 0
        and r["child_rlimit_as_bytes"] == 8 << 30
        and r["output_cap_bytes"] == 16 << 20
        and r["window_s"] == 180
        and r["timeout_s_per_arm"] == 90
        and set(r["arms"]) == {"stock", "OFF", "ON", "invalid"}
        and r["arms"]["invalid"]["exit"] == 25,
        "attribution_program_limits_or_arms",
    )
    for name in ("stock", "OFF", "ON"):
        a = r["arms"][name]
        cpu = a["execution_by_prompt"]
        core.check(
            a["exit"] == 0
            and a["logits_sha256"] == LOGITS
            and a["logits_compared"] == 64
            and a["greedy_ids"] == r["arms"]["stock"]["greedy_ids"]
            and a["cpu_matmuls"] == 16
            and len(cpu) == 2
            and all(
                x["prompt"] == n
                and x["asks"] == x["cpu_kernel_returns"] == x["callback_matches"] > 0
                and x["cpu_graph_dispatches"] >= x["asks"]
                for n, x in enumerate(cpu)
            )
            and sum(x["asks"] for x in cpu) == 16
            and a["mapped_elf_sha256"][IMAGE]
            == (
                build["original_sha256"]
                if name == "stock"
                else build["phases"]["candidate"]["sha256"]
            ),
            "attribution_logits_elf_or_cpu_" + name,
        )
        (mapping,) = a["maps"]
        size, offset, prot, flags = mapping
        hints = [x for x in a["advice"] if x[2] == 3]
        core.check(
            size > 0
            and offset == 0
            and prot == 1
            and flags & 1
            and bool(flags & 0x8000) == (name != "ON")
            and hints == ([] if name == "ON" else [[0, size, 3, 0]]),
            "attribution_mmap_" + name,
        )


def fresh_c55(rows, proof, window, *, now=None):
    now = datetime.now(UTC) if now is None else now
    start = datetime.fromisoformat(rows[0]["utc"])
    end = datetime.fromisoformat(rows[-1]["utc"])
    core.check(
        datetime.fromisoformat(proof["finished_utc"]) < start < end <= now
        and len(rows) == window["samples"]
        and window["span_s"] >= 60,
        "C55_must_follow_CPU_attribution",
    )
    return start.isoformat(), end.isoformat()


def candidate_image(root):
    directory = root.resolve(strict=True) / "candidate"
    core.check(not directory.is_symlink(), "candidate_directory_symlink")
    image = directory / IMAGE
    names = {p.name for p in directory.iterdir() if ".so" in p.name or p.is_dir()}
    core.check(
        names == {"libllama.so", SONAME, IMAGE}
        and image.is_file()
        and not image.is_symlink()
        and all((directory / n).resolve(strict=True) == image for n in ("libllama.so", SONAME)),
        "overlay_contains_other_provider",
    )
    return image


def check_loader(exe, image, stock_dsos, env):
    dynamic_loader = Path("/lib64/ld-linux-x86-64.so.2").resolve(strict=True)
    out = subprocess.check_output([dynamic_loader, "--list", exe], env=env, text=True, timeout=10)
    providers = {}
    for line in out.splitlines():
        m = re.fullmatch(r"\s*(\S+) => (/.+?) \(0x[0-9a-f]+\)", line)
        if m and m[1] in stock_dsos:
            core.check(m[1] not in providers, "duplicate_loader_provider")
            providers[m[1]] = Path(m[2]).resolve(strict=True)
    expected = {
        n: image if n == SONAME else (exe.parent / n).resolve(strict=True) for n in stock_dsos
    }
    core.check(providers == expected, "loader_did_not_select_experimental_and_seven_stock_dsos")
    return core.sha(dynamic_loader)


def nvme_counter(source, sys_class=Path("/sys/class/block")):
    disk = re.fullmatch(r"/dev/(nvme\d+n\d+)(?:p\d+)?(?:\[.*\])?", source)
    core.check(disk is not None, "model_backing_not_an_nvme_namespace")
    dev = sys_class / disk[1]
    major_minor = (dev / "dev").read_text().strip()
    core.check(re.fullmatch(r"\d+:\d+", major_minor), "missing_model_device_id")
    return dev / "stat", major_minor


def bytes_read(stat):
    fields = stat.read_text().split()
    core.check(len(fields) >= 11 and fields[2].isdigit(), "model_device_stat")
    # Linux block statistics field three counts sectors of 512 bytes.
    return int(fields[2]) * 512


class Experiment:
    def __init__(self, root, image, digest, stat, device, raw, record):
        self.root = root
        self.image = image
        self.digest = digest
        self.stat = stat
        self.device = device
        self.raw = raw
        self.record = record
        self.start_bytes = None

    def bind(self, refs, dep_ids):
        self.original = dep_ids[SONAME]
        chosen = core.Reference(refs, self.image, self.digest)
        core.check(chosen.key != self.original, "candidate_is_original_inode")
        self.chosen = chosen
        self.candidate = chosen.key
        dep_ids[SONAME] = self.candidate

    def verify_candidate_stat(self):
        core.check(
            core.stable(os.fstat(self.chosen.file.fileno()))
            == self.chosen.identity
            == core.identity(self.image),
            "candidate_changed_since_authentication",
        )

    def mapping(self, live):
        self.verify_candidate_stat()
        return {
            "candidate_libllama_present": self.candidate in live,
            "stock_libllama_absent": self.original not in live,
        }

    def raw_size(self):
        return sum(p.stat().st_size for p in self.raw.iterdir() if p.is_file())

    @staticmethod
    def require_window(seconds):
        core.check((END - datetime.now(UTC)).total_seconds() > seconds, "physical_window_expired")

    def before_spawn(self):
        self.require_window(190)
        self.verify_candidate_stat()
        core.check(candidate_image(self.root) == self.image, "overlay_changed_before_spawn")
        self.start_bytes = bytes_read(self.stat)
        self.record["model_device_read_start_bytes"] = self.start_bytes

    def watch(self):
        self.require_window(0)
        core.check(self.raw_size() <= 64 * core.MIB, "raw_64MiB")
        delta = bytes_read(self.stat) - self.start_bytes
        core.check(0 <= delta < READ_LIMIT, "model_device_counter_reset_or_1TiB")
        return delta

    def finish(self, record):
        delta = bytes_read(self.stat) - self.start_bytes
        record["raw_size_bytes"] = self.raw_size()
        record["model_device_physical_read_delta_bytes"] = delta
        scope = record["io_stat_delta_by_device"].get(self.device, {})
        record["model_device_cgroup_rbytes"] = scope.get("rbytes")
        core.check(0 <= delta < READ_LIMIT, "model_device_counter_reset_or_1TiB")
        core.check(record["raw_size_bytes"] <= 64 * core.MIB, "raw_64MiB")
        self.require_window(0)


class Profile(full.Profile):
    unit = HERE

    def __init__(self):
        super().__init__(probe=None)
        self.ram_profile = "R0_E20"
        self.paging_cap_bytes = 20 * core.GIB
        self.run_id = "stock-prefault-ready-on-e20"
        self.pass_status = "PASS_EXPERIMENTAL_LAZY_MMAP_E20_READY_ONLY"

    @staticmethod
    def add_arguments(parser):
        for name in ("overlay-root", "attribution-receipt"):
            parser.add_argument("--" + name, type=Path, required=True)

    def runtime_overlay(self, a, exe, stock, mount, env, r):
        root = a.overlay_root.resolve(strict=True)
        overlay = sealed_json(root / "receipt.json", OVERLAY)
        auth = (HERE / "attribution.sha256").read_text().strip()
        proof = sealed_json(a.attribution_receipt, auth)
        check_attribution(proof, overlay)
        image = candidate_image(root)
        original = stock["own_libs_sha256"][SONAME]
        candidate = overlay["phases"]["candidate"]["sha256"]
        core.check(
            overlay["status"] == "PASS_PRIVATE_GOLD_AND_CANDIDATE_BUILD"
            and overlay["server_sha256"] == stock["server_sha256"]
            and len(stock["own_libs_sha256"]) == 8
            and overlay["stock_dsos"] == stock["own_libs_sha256"]
            and core.sha(root / "gold" / IMAGE)
            == overlay["phases"]["gold"]["sha256"]
            == overlay["original_sha256"]
            == original
            and core.sha(image) == candidate != original,
            "experimental_gold_or_build_identity",
        )
        env.update(
            TESY_STOCK_LAZY_MMAP="1", LD_LIBRARY_PATH=str(image.parent) + ":" + str(exe.parent)
        )
        window = core.read(a.policy.parent / "receipt.json")
        window_rows = [
            json.loads(line)
            for line in (a.policy.parent / "samples.jsonl").read_text().splitlines()
        ]
        c55_start, c55_end = fresh_c55(window_rows, proof, window)
        source = window["model_device"]
        core.check(source == mount["source"] and mount["fstype"] == "btrfs", "model_mount_changed")
        stat, device = nvme_counter(source)
        bytes_read(stat)
        r.update(
            scope="EXPERIMENTAL_LAZY_MMAP_FULL_SWA_ASTER_READY",
            experimental_entry_sha256=core.sha(__file__),
            attribution_receipt_sha256=auth,
            attribution_program_sha256=proof["program_sha256"],
            overlay_build_receipt_sha256=OVERLAY,
            stock_libllama_sha256=original,
            gold_libllama_sha256=original,
            candidate_libllama_sha256=candidate,
            lazy_mmap="1",
            loader_sha256=check_loader(exe, image, stock["own_libs_sha256"], env),
            model_device_major_minor=device,
            model_device_read_budget_bytes=READ_LIMIT,
            experiment_deadline_utc=END.isoformat(),
            C55_first_utc=c55_start,
            C55_last_utc=c55_end,
            cpu_gate_finished_utc=proof["finished_utc"],
        )
        return Experiment(root, image, candidate, stat, device, a.new_raw / "raw", r)


if __name__ == "__main__":
    core.cli(paging=True, placement_log=True, ready_profile=Profile())
