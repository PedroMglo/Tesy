#!/usr/bin/env python3
"""Compare complete fixed-token float32 logit rows, with an explicit bitwise gate."""

import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path

from c2_gate import GateError, strict_json


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def rows(path, case, prompt_len, continuation_len, ubatch):
    lines = Path(path).read_text().splitlines()
    if not lines or lines[0] != "case\tphase\tposition\trow":
        raise GateError("invalid row index header")
    actual = []
    for i, line in enumerate(lines[1:]):
        parts = line.split("\t")
        if len(parts) != 4 or parts[0] != case or int(parts[3]) != i:
            raise GateError("row index/case mismatch")
        actual.append((parts[1], int(parts[2])))
    expected = [("prompt", min(k+ubatch, prompt_len)-1) for k in range(0, prompt_len, ubatch)]
    expected += [("continuation", prompt_len+i) for i in range(continuation_len)]
    if actual != expected:
        raise GateError("missing, extra or out-of-order logit position")
    return actual


def compare(reference, candidate, ids_file, case, ubatch, vocab, ref_manifest, cand_manifest):
    if not isinstance(vocab, int) or vocab <= 0 or not isinstance(ubatch, int) or ubatch <= 0:
        raise GateError("bad vocab/batch")
    token_rows = [line.split("\t") for line in Path(ids_file).read_text().splitlines()]
    if any(len(x) != 3 for x in token_rows):
        raise GateError("invalid token ID file")
    selected = [row for row in token_rows if row[0] == case]
    if len(selected) != 1:
        raise GateError("case ID missing or duplicated")
    prompt_len = len(selected[0][1].split(","))
    continuation_len = len(selected[0][2].split(","))
    index_a = rows(str(reference) + ".rows.tsv", case, prompt_len, continuation_len, ubatch)
    index_b = rows(str(candidate) + ".rows.tsv", case, prompt_len, continuation_len, ubatch)
    if index_a != index_b:
        raise GateError("reference/candidate row map differs")
    manifests = [strict_json(Path(p).read_text()) for p in (ref_manifest, cand_manifest)]
    for manifest, prefix in zip(manifests, (reference, candidate)):
        if manifest.get("returncode") != 0 or manifest.get("stop_reason") is not None or not manifest.get("cgroup_limit_enforced"):
            raise GateError("source run failed or lacked cgroup")
        command = manifest.get("command")
        if not isinstance(command, list) or str(prefix) not in command or str(ids_file) not in command:
            raise GateError("source run command does not identify rows and token IDs")
    if manifests[0]["model_id"] != manifests[1]["model_id"] or \
       manifests[0]["model_path"] != manifests[1]["model_path"]:
        raise GateError("model identity differs")
    size = len(index_a) * vocab * 4
    if Path(str(reference) + ".f32").stat().st_size != size or \
       Path(str(candidate) + ".f32").stat().st_size != size:
        raise GateError("float32 row file size mismatch")
    mismatches = []
    with Path(str(reference) + ".f32").open("rb") as ref, \
         Path(str(candidate) + ".f32").open("rb") as cand:
        for i, (phase, position) in enumerate(index_a):
            a = ref.read(vocab*4)
            b = cand.read(vocab*4)
            va = array("f"); va.frombytes(a)
            vb = array("f"); vb.frombytes(b)
            if any(not math.isfinite(x) for x in va) or any(not math.isfinite(x) for x in vb):
                raise GateError("nonfinite float32 logit")
            if a != b:
                diffs = [abs(x-y) for x, y in zip(va, vb)]
                mismatches.append({"row":i,"phase":phase,"position":position,
                                   "max_abs":max(diffs),
                                   "rmse":math.sqrt(sum(x*x for x in diffs)/vocab),
                                   "top1_reference":max(range(vocab), key=va.__getitem__),
                                   "top1_candidate":max(range(vocab), key=vb.__getitem__)})
    return {"schema_version":"c2-numeric-compare-v1", "case":case,
            "prompt_tokens":prompt_len,"continuation_tokens":continuation_len,
            "n_vocab":vocab,"n_rows":len(index_a),
            "bitwise_equal":not mismatches,"mismatch_rows":mismatches,
            "source_sha256": {"token_ids":sha(ids_file),
                              "reference_f32":sha(str(reference)+".f32"),
                              "candidate_f32":sha(str(candidate)+".f32"),
                              "reference_manifest":sha(ref_manifest),
                              "candidate_manifest":sha(cand_manifest)},
            "scope":"fixed token IDs, selected complete rows; no free-generation equivalence"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reference", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--reference-manifest", required=True)
    p.add_argument("--candidate-manifest", required=True)
    p.add_argument("--token-ids", required=True)
    p.add_argument("--case", required=True)
    p.add_argument("--ubatch", required=True, type=int)
    p.add_argument("--vocab", required=True, type=int)
    p.add_argument("--output", required=True)
    p.add_argument("--require-bitwise", action="store_true")
    a = p.parse_args()
    report = compare(a.reference, a.candidate, a.token_ids, a.case, a.ubatch,
                     a.vocab, a.reference_manifest, a.candidate_manifest)
    with Path(a.output).open("x") as out:
        json.dump(report, out, indent=2, allow_nan=False)
        out.write("\n")
    print(json.dumps({k:report[k] for k in ("case","n_rows","n_vocab","bitwise_equal")}))
    return 0 if not a.require_bitwise or report["bitwise_equal"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
