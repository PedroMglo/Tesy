"""Exercise the complete row/post-exit gate and the physical variant controls without a model."""

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import physical as p
from test_compare import make_arm


class PhysicalTests(unittest.TestCase):
    def test_profiles_and_environments_are_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            original = root / p.lazy.SONAME
            original.touch()
            candidate = root / "candidate" / p.lazy.IMAGE
            env = {"TESY_STOCK_LAZY_MMAP": "1"}
            for arm in p.ARMS:
                prof = p.Profile(arm)
                image, sha = p.select_environment(env, arm, root, candidate, "stock", "candidate")
                self.assertEqual(image, original if arm == "S" else candidate)
                self.assertEqual(sha, "stock" if arm == "S" else "candidate")
                self.assertEqual(
                    env.get("TESY_STOCK_LAZY_MMAP"), {"S": None, "A": "0"}.get(arm, "1")
                )
                self.assertEqual(prof.paging_cap_bytes, (20 if arm == "B20" else 10) << 30)
                self.assertEqual(prof.probe.timeout_s, 90)

    def test_only_one_armed_http_request_and_empty_kv(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            (raw / "capture").mkdir(mode=0o700)
            (raw / "server.log").write_text("listening on http://127.0.0.1:12345")
            reply = {
                "id_slot": 0,
                "tokens_predicted": 1,
                "tokens_evaluated": 16,
                "stop": True,
                "truncated": False,
                "tokens": [3],
                "generation_settings": {"temperature": 0, "n_probs": 0},
                "timings": {
                    "cache_n": 0,
                    "prompt_n": 16,
                    "predicted_n": 1,
                    "prompt_ms": 1,
                    "predicted_ms": 0,
                },
            }
            connection = MagicMock()
            response = connection.getresponse.return_value
            response.status = 200
            response.read.return_value = json.dumps(reply).encode()
            progress = {}
            probe = p.Probe("S")
            probe.ids = list(range(16))

            def validate_post(method, path, body, headers):
                req = json.loads(body)
                self.assertEqual(
                    (method, path, req["n_probs"], req["n_predict"]), ("POST", "/completion", 0, 1)
                )
                self.assertEqual(req["prompt"], probe.ids)
                self.assertEqual((raw / "capture/ARM").read_bytes(), p.ARM)

            connection.request.side_effect = validate_post
            with (
                patch.object(p.http.client, "HTTPConnection", return_value=connection),
                patch.object(p.split, "owned_listener") as listener,
            ):
                from threading import Event

                result = probe.run(123, raw, Event(), progress)
            listener.assert_called_once_with(123, 12345)
            self.assertEqual(progress, {"http_requests_sent": 1, "sampling_tokens_requested": 1})
            self.assertEqual(result["owned_server_pid"], 123)
            self.assertEqual(result["sampled_id"], 3)
            self.assertEqual(result["prompt_n"], 16)
            connection.request.assert_called_once()
            connection.close.assert_called_once()

    def test_unique_atomic_marker(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p.arm_once(root)
            self.assertEqual((root / "ARM").read_bytes(), p.ARM)
            with self.assertRaisesRegex(ValueError, "already_used"):
                p.arm_once(root)

    def test_preload_and_lib_selection_at_ready(self):
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as d:
            raw = Path(d)
            file = raw / "observer"
            file.write_bytes(b"mock")
            e = p.Experiment(raw, None, None, None, None, raw, {})
            e.observer = file
            with file.open("rb") as f, patch.object(e, "verify_candidate_stat"):
                e.observer_ref = SimpleNamespace(key=3, file=f, identity=p.core.identity(file))
                e.candidate, e.original = 1, 2
                for arm in p.ARMS:
                    e.arm = arm
                    allowed = 2 if arm == "S" else 1
                    self.assertTrue(all(e.mapping({3, allowed}).values()))
                    self.assertFalse(all(e.mapping({allowed}).values()))
                    self.assertFalse(all(e.mapping({1, 2, 3}).values()))

    def test_post_exit_preserves_true_float32_bitwise_comparison(self):
        for arm, changes, fails in (
            ("S", {}, False),
            ("A", {}, False),
            ("A", {"sampled_id": 1}, True),
            ("B", {"bad_bit": True}, True),
        ):
            with self.subTest(arm=arm, changes=changes), tempfile.TemporaryDirectory() as d:
                report, private = make_arm(Path(d), arm, difference=bool(changes.get("bad_bit")))
                raw = private / "raw"
                record = json.loads((report / "receipt.json").read_text())
                folder = raw / "capture"
                folder.mkdir()
                p.arm_once(folder)
                cap = json.loads((raw / "capture.json").read_text())
                cap["prearm_calls"] = 0
                (raw / "capture.json").write_text(json.dumps(cap))
                for name in ("capture.json", "row.f32"):
                    (raw / name).rename(folder / name)
                if "sampled_id" in changes:
                    record["after_ready"]["sampled_id"] = changes["sampled_id"]
                baseline = bytearray((folder / "row.f32").read_bytes())
                baseline[0:4] = bytes(4)
                if fails:
                    with self.assertRaises(ValueError):
                        p.collect_capture(raw, record, bytes(baseline))
                else:
                    p.collect_capture(raw, record, None if arm == "S" else bytes(baseline))
                    self.assertTrue(record["comparison"]["finite_candidate"])
                    self.assertTrue(record["comparison"]["bitwise_equal"])
                    self.assertEqual(record["row_file"], "row.f32")

    def test_later_arm_requires_complete_sealed_equal_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            family = Path(d)
            with self.assertRaisesRegex(ValueError, "missing"):
                p.prior_rows(family, "A", {}, p.END)
            past = []
            for arm in ("S", "A", "B"):
                report, private = make_arm(family, arm, difference=(arm == "B"))
                report.rename(family / (arm + ".report"))
                private.rename(family / (arm + ".private"))
                path = family / (arm + ".report") / "receipt.json"
                data = json.loads(path.read_text())
                data.update(prior_receipts_sha256=list(past), family_started_utc=p.END.isoformat())
                path.write_text(json.dumps(data))
                past.append(p.core.sha(path))
            self.assertEqual(p.prior_rows(family, "B", {}, p.END)[0], past[:2])
            with self.assertRaisesRegex(ValueError, "mismatch"):
                p.prior_rows(family, "B20", {}, p.END)

    def test_admission_reserves_one_ninety_second_http_request(self):
        e = p.Experiment(None, None, None, None, None, None, {})
        now = p.datetime(2026, 11, 25, 4, 50, tzinfo=p.UTC)
        with patch.object(p, "datetime") as clock:
            clock.now.return_value = now
            for remaining, valid in ((340, False), (341, True)):
                e.deadline = now + timedelta(seconds=remaining)
                if valid:
                    e.require_window(250)
                else:
                    with self.assertRaisesRegex(ValueError, "family_clock"):
                        e.require_window(250)


if __name__ == "__main__":
    unittest.main()
