"""Package the frozen vertical-integration raw evidence without model/build files."""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path

STOCK_ROOT = Path("results/full-stock-chat-eval-valid-20260924T222803Z")
BLOCKER_ROOT = Path("results/vertical-live-diagnostic-20260924T215315Z")
CAPACITY_REPORT = Path("results/vertical-capacity-20260924T220300Z/report.json")
STOCK_SUMMARY_SHA = "47d63e066c45bd52f03302b9e19fce1f14de5b2e39847bfc66a8555c3830fbff"
STOCK_LOGITS_SHA = "52c37d27a8249466a8507211267e5c33fa144eaab060c16bae299bb6d7df7b46"
CANDIDATE_LOGITS_SHA = "a4882f71f52e5fe7339c1792855245ccd4aa8c09a6c72f0725e2aa54bbf2fe05"

STOCK_FILES = (
    "run.json", "sse-events.jsonl", "stream.sse", "runtime-provenance.json",
    "resources.jsonl", "argv.json", "placement-capacity.json",
    "input-sha256.txt", "model.json",
)
BLOCKER_FILES = (
    "failure.json", "token-0-candidate-logits.f32", "token-0-stock-logits.f32",
    "runtime-provenance.json", "resources.jsonl", "tool.stderr.txt",
    "argv.json", "build-provenance.json",
)
_HOME_PATH = re.compile(r"/home/pmglo/[A-Za-z0-9_./-]+")
_SECRET = re.compile(
    r"(?:ghp_[A-Za-z0-9]{20}|github_pat_[A-Za-z0-9_]{20}|"
    r"AKIA[0-9A-Z]{16}|BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY|"
    r"Authorization:|Cookie:|HF_TOKEN|OPENAI_API_KEY)",
    re.IGNORECASE,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize_doctor(raw: bytes) -> tuple[bytes, dict]:
    doctor = json.loads(raw)
    if doctor["reference_check"]["status"] != "PASS":
        raise ValueError("doctor host admission did not PASS")
    if doctor["snapshot"]["virtualization"]["status"] != "PHYSICAL":
        raise ValueError("doctor host is not physical")
    public = copy.deepcopy(doctor)
    storage = public["snapshot"].get("storage_topology", {})
    removed = "lsblk" in storage
    storage.pop("lsblk", None)
    public["public_redaction"] = {
        "omitted_field": "snapshot.storage_topology.lsblk",
        "reason": "contains unrelated mountpoint paths",
        "original_sha256": _sha(raw),
        "was_present": removed,
    }
    encoded = (json.dumps(public, indent=2, sort_keys=True) + "\n").encode()
    return encoded, public["public_redaction"]


def _check_text(data: bytes, *, allowed_prefixes: tuple[str, ...], name: str) -> None:
    text = data.decode("utf-8", errors="strict")
    if _SECRET.search(text):
        raise ValueError(f"possible secret in {name}")
    for match in _HOME_PATH.finditer(text):
        if not any(
            match.group() == prefix.rstrip("/") or match.group().startswith(prefix)
            for prefix in allowed_prefixes
        ):
            raise ValueError(f"unrelated home path in {name}")


def _read_file(root: Path, relative: Path) -> bytes:
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"missing, non-file or symlink evidence: {relative}")
    return path.read_bytes()


def _add_bytes(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = 0o644
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    archive.addfile(info, io.BytesIO(data))


def build_bundle(repo_root: Path, output: Path) -> dict:
    root = repo_root.resolve(strict=True)
    if output.exists():
        raise ValueError("refusing to replace evidence bundle")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip():
        raise ValueError("Tesy worktree must be clean")
    if subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root / ".deps/llama.cpp", text=True
    ).strip() != "4e416ee7308dd6b581796f1a6241276cd5982691":
        raise ValueError("llama.cpp pin mismatch")
    if subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=root / ".deps/llama.cpp", text=True
    ).strip():
        raise ValueError("llama.cpp worktree not clean")

    summary = _read_file(root, STOCK_ROOT / "summary-final.json")
    if _sha(summary) != STOCK_SUMMARY_SHA:
        raise ValueError("stock summary SHA mismatch")
    model_path = json.loads(_read_file(
        root, STOCK_ROOT / "rep1-extraction-long-ngl0/model.json"
    ))["observed"]["path"]
    allowed = (str(root) + "/", str(Path(model_path).parent) + "/")

    entries: dict[str, bytes] = {}
    redactions: list[dict] = []

    def put(relative: Path, *, doctor: bool = False) -> None:
        raw = _read_file(root, relative)
        name = relative.as_posix()
        if doctor:
            data, redaction = sanitize_doctor(raw)
            name = name.removesuffix("doctor.json") + "doctor-public.json"
            redactions.append({"published_path": name, **redaction})
        else:
            data = raw
        if not name.endswith(".f32"):
            _check_text(data, allowed_prefixes=allowed, name=name)
        entries[name] = data

    put(STOCK_ROOT / "summary-final.json")
    for rep in range(1, 6):
        for workload in ("extraction-long", "code-short"):
            for ngl in (0, 12):
                run = STOCK_ROOT / f"rep{rep}-{workload}-ngl{ngl}"
                for filename in STOCK_FILES:
                    put(run / filename)
                put(run / "doctor.json", doctor=True)
    for filename in BLOCKER_FILES:
        put(BLOCKER_ROOT / filename)
    put(BLOCKER_ROOT / "doctor.json", doctor=True)
    put(CAPACITY_REPORT)

    if _sha(entries[(BLOCKER_ROOT / "token-0-stock-logits.f32").as_posix()]) != STOCK_LOGITS_SHA:
        raise ValueError("stock logits SHA mismatch")
    candidate_key = (BLOCKER_ROOT / "token-0-candidate-logits.f32").as_posix()
    if _sha(entries[candidate_key]) != CANDIDATE_LOGITS_SHA:
        raise ValueError("candidate logits SHA mismatch")

    manifest = {
        "schema": "tesy.vertical_raw_evidence_bundle.v1",
        "classification": "MEASURED_PUBLIC_RAW_WITH_EXPLICIT_HOST_REDACTION",
        "source_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "entry_count": len(entries),
        "entries": [
            {"path": name, "size_bytes": len(data), "sha256": _sha(data)}
            for name, data in sorted(entries.items())
        ],
        "redactions": redactions,
        "excluded": [
            "model weights", "build products", "caches", "full original doctor.json",
            "exact sampled token-ID vector (not captured by the SSE endpoint)",
        ],
        "claim_boundary": (
            "Original campaign roots remain byte-identical locally. Public doctor copies "
            "omit unrelated mountpoint enumeration; all other listed entries are raw."
        ),
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    with tarfile.open(output, mode="x:gz") as archive:
        for name, data in sorted(entries.items()):
            _add_bytes(archive, name, data)
        _add_bytes(archive, "bundle-manifest.json", manifest_bytes)
    return {
        "archive_path": str(output),
        "archive_size_bytes": output.stat().st_size,
        "archive_sha256": _sha(output.read_bytes()),
        "entry_count": len(entries),
        "redacted_doctor_count": len(redactions),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build_bundle(args.repo_root, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
