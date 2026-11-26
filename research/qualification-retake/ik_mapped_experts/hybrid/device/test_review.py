import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = spec_from_file_location("tesy_ik_device_review", HERE / "review.py")
r = module_from_spec(spec)
spec.loader.exec_module(r)

mock_trace = run_path(str(HERE.parent / "client/test_grade.py"))["artificial"]
POL = dict(
    gpu=dict(uuid="GPU-test", warning_c=80, stop_c=90, memory_stop_total_mib=8000),
    cpu=dict(warning_c=90, stop_c=95),
    nvme=[dict(sensor="nvme0", warning_c=60, stop_c=70)],
    memory=dict(reserve_bytes=1 << 30),
)
START = datetime(2020, 1, 1, tzinfo=UTC)
OBS = dict(
    thermal=dict(cpu_tctl_c=45, nvme_composite_by_sensor={"nvme0": 33}),
    gpu=dict(temperature_c=40, used_mib=180, uuid="GPU-test", power_w=6),
    power=dict(source="AC", profile="performance"),
    mem_available_bytes=20 << 30,
)


def monitor_row(index, phase, owners, attempt=1):
    return dict(
        phase=phase,
        attempt=attempt,
        elapsed_s=(index + 1) / 10,
        peak_bytes=100000,
        utc=(START + timedelta(seconds=index / 10)).isoformat(),
        observation=OBS | {"gpu_owners": owners},
    )


def checks():
    return [
        monitor_row(i, *spec)
        for i, spec in enumerate(
            (
                ("running", []),
                ("entry", []),
                ("active", [], 1),
                ("active", [42], 2),
                ("running", [42]),
                ("finish", [42]),
                ("after_exit", []),
            )
        )
    ]


def put(file, data):
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(data, sort_keys=True))
    return r.digest(file)


def jsonl(file, rows):
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("".join(json.dumps(v) + "\n" for v in rows))
    return r.digest(file)


class Review(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        top = Path(t.name)
        self.a = SimpleNamespace(
            **{n: top / n for n in ("family", "cpu", "client", "c55", "prepared")}
        )
        self.a.family.mkdir()

    def test_owner_and_order(self):
        data = checks()
        self.assertTrue(r.check_window(data, True, 42, POL)["after_exit"])
        for i, field, value in (
            (3, "attempt", 1),
            (4, "elapsed_s", 5),
            (5, "phase", "active"),
            (6, "attempt", 2),
        ):
            bad = list(data)
            bad[i] = bad[i] | {field: value}
            with self.assertRaises(ValueError):
                r.check_window(bad, True, 42, POL)
        for owners in ([13], [13, 42], []):
            bad = list(data)
            bad[5] = monitor_row(5, "finish", owners)
            with self.assertRaises(ValueError):
                r.check_window(bad, True, 42, POL)

    def test_pre_spawn_and_tamper(self):
        a = self.a
        f = {"status": "FAIL_PRESERVED", "arms": {}, "reason": "refused", "raw_sha256": {}}
        a.family_sha256 = put(a.family / "receipt.json", f)
        self.assertEqual(r.review(a)["launches"], 0)
        (a.family / "new").touch()
        with self.assertRaisesRegex(ValueError, "inventory"):
            r.review(a)

    def test_complete_archive_and_first_failed_grade(self):
        a = self.a
        cpu = a.cpu / "native"
        cpu.mkdir(parents=True)
        tx, lg = mock_trace("CPU", cpu)
        (a.cpu / "stdout").write_text(tx)
        (a.cpu / "stderr").write_text(lg)
        cpu_grade = r.native_grade("CPU", cpu)
        c = dict(
            status="PASS_TINY_HYBRID_CPU_REFERENCE",
            model_sha256=r.API["TINY"],
            grade=cpu_grade,
            stdout_sha256=r.digest(a.cpu / "stdout"),
            stderr_sha256=r.digest(a.cpu / "stderr"),
        )
        shac = put(a.cpu / "receipt.json", c)
        exe = "/vanished/scope/hybrid-client"
        lib = "/vanished/scope/libggml.so"
        ident = {
            exe: dict(stat=[1, 3, 100, 2, 3], sha256="exe"),
            lib: dict(stat=[1, 4, 100, 2, 3], sha256="lib"),
        }
        b = dict(
            status="PASS_TINY_HYBRID_CLIENT_BUILD",
            variant="cuda",
            dso_build_sha256="DSO",
            sources={"grade.py": r.digest(HERE.parent / "client/grade.py")},
            binary_sha256="exe",
            binary="hybrid-client",
            closure={"libggml.so": {"file": lib, "sha256": "lib"}},
        )
        shab = put(a.client / "receipt.json", b)
        f = dict(
            status=r.PASS,
            arms={},
            unit="unit",
            client_sha256=shab,
            cpu_sha256=shac,
            model_sha256=r.API["TINY"],
            dso_sha256="DSO",
            c55_sha256="C55",
            commit="abc",
            tree="abc",
            supervisor_sha256=r.digest(HERE / "run.py"),
            protocol_sha256=r.digest(HERE / "protocol.md"),
            provider_identity=ident,
            max_scope_bytes=100000,
            swap_peak_bytes=0,
            memory_events_local={"high": 0, "max": 0, "oom": 0, "oom_kill": 0},
        )
        f["prepared_sha256"] = put(a.prepared / "receipt.json", f | {"status": "PREPARED_ONLY"})
        for mode in r.MODES:
            arm = a.family / mode
            nd = arm / "native"
            nd.mkdir(parents=True)
            tx, lg = mock_trace(mode, nd)
            (arm / "stdout").write_text(tx)
            (arm / "stderr").write_text(lg)
            (nd / "maps").write_text(
                "aa-bb r-xp 0 00:01 3 " + exe + "\ncc-dd r-xp 0 00:01 4 " + lib + "\n"
            )
            rid = "unit-" + mode.lower()
            ip = a.family / "raw" / (rid + ".start-inventory.jsonl")
            rows = [
                dict(
                    observation=OBS,
                    run_id=rid,
                    elapsed_s=i,
                    utc=(START + timedelta(seconds=i)).isoformat(),
                )
                for i in range(61)
            ]
            inv = dict(
                schema="c118-per-arm-start-inventory-v2",
                run_id=rid,
                path="/old/raw/" + ip.name,
                sha256=jsonl(ip, rows),
                sample_count=61,
                duration_s=60,
                last_utc=rows[-1]["utc"],
                policy_sha256=r.API["INV"].require_inventory.__globals__["digest"](POL),
                cap_bytes=r.API["CAP"],
                expected_power=r.API["INV"].POWER,
            )
            grade = r.native_grade(mode, nd)
            s = dict(
                grade=grade,
                starts=1,
                admission=inv,
                returncode=0,
                child_gone=True,
                wall_s=1,
                pid=42,
                observed_handoffs=3,
                A_providers=[lib],
                F_providers=[lib],
                sampled_vram_mib_max=180,
                stdout_sha256=r.digest(arm / "stdout"),
                stderr_sha256=r.digest(arm / "stderr"),
                monitor_sha256=jsonl(arm / "monitor.jsonl", checks()),
            )
            if mode == "RESIDENT":
                s["cpu_comparison"] = r.GRADE["compare_arms"](cpu, cpu_grade, nd, grade)
                resident = (nd, grade)
            else:
                s["resident_comparison"] = r.GRADE["compare_arms"](*resident, nd, grade)
            f["arms"][mode] = s
            put(arm / "grade.json", s)

        def finish():
            f["raw_sha256"] = {
                p.relative_to(a.family).as_posix(): r.digest(p)
                for p in a.family.rglob("*")
                if p.is_file() and p != a.family / "receipt.json"
            }
            a.family_sha256 = put(a.family / "receipt.json", f)
            with patch.dict(r.API, c55=lambda _: (POL, START)):
                return r.review(a)

        passed = finish()
        self.assertEqual(passed["status"], "REPRODUCED_TINY_HYBRID_GPU_FIXTURE")
        self.assertTrue(passed["arms"]["BANK9"]["resident_comparison"]["bitwise"])
        self.assertEqual(passed["arms"]["BANK7"]["C118"]["sample_count"], 61)
        ar = a.family / "BANK7"
        (ar / "grade.json").unlink()
        (ar / "stdout").write_text("incomplete")
        s = f["arms"]["BANK7"]
        s.pop("grade")
        s.pop("resident_comparison")
        s.update(stdout_sha256=r.digest(ar / "stdout"), returncode=1)
        f.update(status="FAIL_PRESERVED", reason="terminal")
        failed = finish()
        self.assertEqual(failed["status"], "REVIEWED_PRESERVED_FAILURE")
        self.assertEqual(failed["launches"], 3)
        self.assertEqual(failed["arms"]["BANK7"]["status"], "STARTED_BEFORE_FAIL")
        self.assertIn("grade", failed["arms"]["BANK7"]["issues"][0])


if __name__ == "__main__":
    unittest.main()
