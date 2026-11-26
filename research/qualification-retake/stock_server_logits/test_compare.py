import json
import math
import struct
import tempfile
import unittest
from pathlib import Path

import compare as c


def store(path, obj):
    path.write_bytes(json.dumps(obj).encode())


def make_arm(base, name, *, difference=False):
    report = base / ("report-" + name)
    parent = base / ("artifacts-" + name)
    raw = parent / "raw"
    raw.mkdir(parents=True)
    report.mkdir()
    row = bytearray(c.VOCAB * 4)
    struct.pack_into("<f", row, 4 * 3, 3.0)
    if difference:
        struct.pack_into("<f", row, 0, -0.0)
    (raw / "row.f32").write_bytes(row)
    prompt = list(range(16))
    req = dict(prompt=prompt, n_predict=1, temperature=0, seed=42, id_slot=0, return_tokens=True)
    store(raw / "request.json", req)
    counts = dict(tokens_evaluated=16, tokens_predicted=1, id_slot=0)
    timings = dict(cache_n=0, prompt_n=16, predicted_n=1)
    store(
        raw / "response.json",
        dict(timings=timings, **counts, tokens=[3], stop=True, truncated=False),
    )
    provider = c.STOCK if name == "S" else c.CAND
    store(
        raw / "capture.json",
        dict(
            status="PASS",
            reason="",
            profile="stock120b",
            armed_calls=1,
            row_index=15,
            n_vocab=c.VOCAB,
            row_bytes=len(row),
            argmax=3,
            caller_offset=0x26951F,
            caller_sha256=c.CALLER,
            provider_sha256=provider,
            row_sha256=c.digest(row),
        ),
    )
    hashes = {p.name: c.digest(p.read_bytes()) for p in raw.iterdir()}
    http = dict(
        http_status=200,
        request_sha256=hashes["request.json"],
        response_sha256=hashes["response.json"],
        sampled_id=3,
        **counts,
        **timings,
    )
    data = dict(
        status="PASS_STOCK_SERVER_RAW_LOGITS_ARM",
        child_gone=True,
        returncode=0,
        server_starts=1,
        http_requests_sent=1,
        sampling_tokens_requested=1,
        arm=name,
        cap_bytes=(20 if name == "B20" else 10) * 2**30,
        server_sha256=c.SERVER,
        active_libllama_sha256=provider,
        observer_sha256="f" * 64,
        row_file="row.f32",
        raw_sha256=hashes,
        request_sha256=hashes["request.json"],
        prompt_ids_sha256=c.digest(struct.pack("<16i", *prompt)),
        after_ready=http,
        row_sha256=hashes["row.f32"],
        greedy_id=3,
        sampled_id=3,
        measurement_commit="0" * 40,
        measurement_tree="1" * 40,
    )
    store(report / "receipt.json", data)
    return report, parent


class Comparisons(unittest.TestCase):
    def test_each_envelope_and_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            pairs = [make_arm(Path(tmp), name) for name in c.ARMS]
            self.assertEqual(c.compare_family(pairs)["status"], "PASS_E10_AND_E20_TRANSFER_BITWISE")
            self.assertEqual(c.compare_family(pairs[:3])["status"], "PASS_E10_BITWISE")
            self.assertEqual(c.compare_family(pairs[:1])["status"], "PASS_PREFIX")
            self.assertEqual(
                c.compare_family(pairs, expected_prompt_sha256="1" * 64)["status"], "FAIL_PRESERVED"
            )
            self.assertEqual(c.compare_family([pairs[1]])["status"], "FAIL_PRESERVED")

    def test_bitwise_signed_zero_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pairs = [make_arm(root, "S"), make_arm(root, "A", difference=True)]
            result = c.compare_family(pairs)
            self.assertEqual(result["status"], "FAIL_PRESERVED")
            self.assertEqual(result["not_run"], ["B", "B20"])
            diff = result["arms"][1]
            self.assertEqual(
                (diff["different_f32_bits"], diff["max_abs"], diff["candidate_argmax"]), (1, 0, 3)
            )
        data = struct.pack("<2f", 2, math.inf)
        x = c.summarize(data, data, vocab=2)
        self.assertFalse(x["finite_gold"])
        self.assertIsNone(x["max_abs"])
        with self.assertRaises(ValueError):
            c.summarize(data[:-1], data, vocab=2)

    def test_streamed_summary_matches_full_arithmetic(self):
        a, b = (-0.0, 1.5, -999.0, 1.5), (0.0, 1.5, -998.75, -3.0)
        reference, candidate = struct.pack("<4f", *a), struct.pack("<4f", *b)
        diff = c.summarize(reference, candidate, vocab=4)
        delta = [abs(x - y) for x, y in zip(a, b, strict=True)]
        self.assertEqual(
            (diff["max_abs"], diff["mean_abs"], diff["rmse"]),
            (max(delta), math.fsum(delta) / 4, math.sqrt(math.fsum(x * x for x in delta) / 4)),
        )
        self.assertEqual(
            (diff["gold_argmax"], diff["candidate_argmax"], diff["different_f32_bits"]), (1, 1, 3)
        )
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "blob"
            for data in (b"", b"1234"):
                p.write_bytes(data)
                with self.assertRaises(ValueError):
                    c.bounded(p, 3)
            p.write_bytes(b"123")
            self.assertEqual(c.bounded(p, 3), b"123")

    def test_bad_receipt_capture_and_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            report, parent = make_arm(Path(tmp), "S")
            file = report / "receipt.json"
            orig = json.loads(file.read_text())
            for field, value in (
                ("child_gone", False),
                ("returncode", 9),
                ("greedy_id", 1),
                ("active_libllama_sha256", c.CAND),
                ("row_file", "../row.f32"),
                ("server_starts", 2),
                ("cap_bytes", 20 << 30),
            ):
                with self.subTest(field=field):
                    store(file, orig | {field: value})
                    with self.assertRaises(ValueError):
                        c.verified_row(report, parent)
            store(file, orig)
            capture = parent / "raw/capture.json"
            msg = json.loads(capture.read_text())
            saved = capture.read_bytes()
            for k, v in (
                ("argmax", 1),
                ("profile", "mock"),
                ("armed_calls", 2),
                ("caller_offset", 0),
                ("provider_sha256", c.CAND),
                ("row_index", 0),
            ):
                store(capture, msg | {k: v})
                rec = orig | {
                    "raw_sha256": orig["raw_sha256"]
                    | {"capture.json": c.digest(capture.read_bytes())}
                }
                store(file, rec)
                with self.assertRaises(ValueError):
                    c.verified_row(report, parent)
            capture.write_bytes(saved)
            store(file, orig)
            resp = parent / "raw/response.json"
            resp.write_bytes(resp.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "changed raw evidence"):
                c.verified_row(report, parent)


if __name__ == "__main__":
    unittest.main()
