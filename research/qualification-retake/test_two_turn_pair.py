"""Local synthetic contract tests. No model, external reference, or physical result."""

import hashlib
import json
import tempfile
import unittest
from importlib import import_module
from pathlib import Path

pair = (
    import_module(".two_turn_pair", __package__) if __package__ else import_module("two_turn_pair")
)


def save(path, value):
    raw = json.dumps(value).encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


class PairFixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.specs = [{"required": ["key"]}, {"required": ["target"]}]
        self.users = [[{"role": "user", "content": f"fixture-{i}"}] for i in range(2)]
        turn1 = {"role": "assistant", "content": "key"}
        self.hist = pair.assistant_history_messages(self.users[0], turn1, self.users[1])
        self.ids = [list(range(n)) for n, _, _ in pair.COUNTS]
        self.manifest = {
            "turns": [
                {"prompt_ids_sha256": pair.digest(ids), "messages_sha256": pair.digest(msg)}
                for ids, msg in zip(self.ids, [self.users[0], self.hist], strict=True)
            ]
        }
        self.inputs = self.manifest, self.specs, self.users, self.hist

    def build(self, mode="natural", mutation=None):
        pins, protocols, maps = {}, {}, {}
        for n, (role, engine) in enumerate(pair.ROLES.items(), 1):
            private = self.root / role
            private.mkdir()
            libraries = {"fixture": str(n) * 64}
            maps[role] = libraries
            ident = {
                "model_sha256": pair.MODEL,
                "binary_sha256": str(n) * 64,
                "backend_tree": str(n) * 40,
                "library_manifest_sha256": pair.digest(libraries),
            }
            proto = {"engine": engine, "policy": pair.POLICY, "identity": ident}
            pins[role] = save(private / "protocol.json", proto)
            protocols[role] = proto
        h = save(
            self.root / "pair.json",
            {
                "schema": "tesy-two-turn-pair-v1",
                "mode": mode,
                "arms": pins,
                "input_sha256": pair.digest(self.manifest),
            },
        )
        for role in pair.ROLES:
            private = self.root / role
            run = "fixture-" + role
            launch = {"pid": 187, "start_ticks": 42}
            proto = protocols[role]
            pre = {
                "protocol_sha256": pins[role],
                "protocol": proto,
                "run_id": run,
                "model_sha256_prior_verified": pair.MODEL,
                "server_model_id": "fixture",
                "launch_identity": launch,
                "config": {"n_ctx": 8192},
                "parallel_slots": 1,
                "binary_sha256": proto["identity"]["binary_sha256"],
                "backend_tree": proto["identity"]["backend_tree"],
                "actually_loaded_backend_libraries_sha256": maps[role],
            }
            raw = {
                "returncode": 0,
                "stop_reasons": [],
                "preflight": pre,
                "launch_identity": launch,
                "results": [],
            }
            requests, tokens = {}, {}
            for i, (key, (n, cached, new)) in enumerate(zip(pair.IDS, pair.COUNTS, strict=True)):
                if role == "r0" and i == 1 and mutation == "cache":
                    cached += 1
                    new -= 1
                seq = self.ids[i].copy()
                if role == "r0" and i == 1 and mutation == "ids":
                    seq[-1] += 1
                messages = [self.users[0], self.hist][i]
                if i and mode == "natural":
                    messages = pair.assistant_history_messages(
                        self.users[0], raw["results"][0]["message"], self.users[1]
                    )
                requests[key] = pair.payload("fixture", messages)
                tokens[key] = seq
                first = "altered key" if role == "r0" and mutation == "history" else "key"
                text = first if i == 0 else ("miss" if role == "r0" else "target")
                row = {
                    "id": key,
                    "source_task_id": key,
                    "finish_reason": "stop",
                    "started_s": 2 * i,
                    "ended_s": 2 * i + 1,
                    "message": {
                        "role": "assistant",
                        "content": text,
                        "reasoning_content": "target",
                    },
                    "stream_metrics": {"done_observed": True, "first_final_content_chunk_s": 0.2},
                    "usage": {
                        "prompt_tokens": n,
                        "completion_tokens": 1,
                        "total_tokens": n + 1,
                        "prompt_tokens_details": {"cached_tokens": cached},
                    },
                    "timings": {"cache_n": cached, "prompt_n": new, "predicted_n": 1},
                }
                raw["results"].append(row)
            if role == "r0" and mutation == "missing_turn":
                raw["results"].pop()
            rec = {
                "schema": "tesy-two-turn-capture-v1",
                "model_launch_observed": True,
                "run_id": run,
                "pair_sha256": h,
                "protocol_sha256": pins[role],
                "raw_sha256": save(private / "raw.json", raw),
                "requests_sha256": save(private / "requests.json", requests),
                "tokenization_sha256": save(private / "tokenization.json", tokens),
            }
            save(private / "receipt.json", rec)
        return h

    def test_only_final_content_is_graded(self):
        result = pair.compare(self.root, self.build(), self.inputs)
        self.assertEqual(
            (result["status"], result["second_turn"]), ("DIAGNOSTICO_PAIRED", "ONLY_R0_FAILS")
        )

    def test_divergent_official_ids(self):
        self.assertEqual(
            pair.compare(self.root, self.build(mutation="ids"), self.inputs)["status"],
            "INCONCLUSIVE",
        )

    def test_divergent_cache_with_equal_total(self):
        self.assertEqual(
            pair.compare(self.root, self.build(mutation="cache"), self.inputs)["status"],
            "INCONCLUSIVE",
        )

    def test_missing_second_envelope_is_failure(self):
        with self.assertRaises(ValueError):
            pair.compare(self.root, self.build(mutation="missing_turn"), self.inputs)

    def test_missing_reference_receipt_is_not_evidence(self):
        sha = self.build()
        (self.root / "reference" / "receipt.json").unlink()
        with self.assertRaises(FileNotFoundError):
            pair.compare(self.root, sha, self.inputs)

    def test_natural_history_change_is_inconclusive(self):
        self.assertEqual(
            pair.compare(self.root, self.build(mutation="history"), self.inputs)["status"],
            "INCONCLUSIVE",
        )

    def test_fixed_history_remains_diagnostic_after_first_response_changes(self):
        result = pair.compare(self.root, self.build(mode="fixed", mutation="history"), self.inputs)
        self.assertEqual((result["status"], result["mode"]), ("DIAGNOSTICO_PAIRED", "fixed"))

    def test_wrong_frozen_plan_digest(self):
        self.build()
        with self.assertRaises(ValueError):
            pair.compare(self.root, "0" * 64, self.inputs)


if __name__ == "__main__":
    unittest.main()
