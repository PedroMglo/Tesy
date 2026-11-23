#!/usr/bin/env python3
"""Fail if a published Scale Lab campaign lacks a reviewed, current report."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from reportlib import (
    ROOT, EvidenceError, check_derived, folder, git_blob, read, require,
    sha, validate, verify,
)

FINAL = re.compile(r"C([0-9]{1,2})-FINAL-[0-9]{8}\.md\Z")


def check(repo: Path, root: Path = ROOT) -> list[str]:
    repo = repo.resolve()
    root = root.resolve()
    require((repo / "research").is_dir(), "RESEARCH_DIRECTORY_REQUIRED")
    registry = read(root / "registry.json")
    catalog = read(root / "sources/catalog.json")
    validate(root, "registry", registry)
    validate(root, "sources", catalog)
    by_path = {entry["path"]: entry for entry in catalog["sources"]}
    require(len(by_path) == len(catalog["sources"]), "DUPLICATE_SOURCE_PATH")
    finals = sorted(p for p in (repo / "research").iterdir()
                    if p.is_file() and FINAL.fullmatch(p.name))
    require(finals, "NO_FINAL_CAMPAIGNS_FOUND")
    result = []
    for final in finals:
        number = f"{int(FINAL.fullmatch(final.name).group(1)):02d}"
        matches = [entry for entry in registry["reports"]
                   if entry["kind"] == "campaign" and entry["id"].startswith("C" + number + "-")]
        require(len(matches) == 1, f"REPORT_REQUIRED_FOR_C{number}: {final.name}")
        report_id = matches[0]["id"]
        path = "research/" + final.name
        require(path in by_path, "FINAL_SOURCE_NOT_CATALOGED: " + path)
        source = by_path[path]
        data = final.read_bytes()
        require(len(data) == source["bytes"] and sha(data) == source["sha256"]
                and git_blob(data) == source["git_blob_sha1"],
                "FINAL_SOURCE_STALE: " + path)
        report = folder(root, report_id)
        meta = read(report / "campaign.json")
        spec = read(report / "evidence-spec.json")
        require(meta["editorial_state"] == "REVIEWED", "REPORT_NOT_REVIEWED: " + report_id)
        require(source["commit"] in meta["evidence_snapshot_commits"],
                "FINAL_COMMIT_NOT_PINNED: " + report_id)
        require(any(x["source"] == source["id"] and x["path"] == path
                    for x in spec["source_contracts"]),
                "FINAL_NOT_USED_AS_EVIDENCE: " + report_id)
        v = verify(root, report_id)
        check_derived(v)
        audit = read(report / "audit.json")
        validate(root, "audit", audit)
        require(audit["status"] == "REVIEWED" and audit["claims_reviewed"]
                and audit["all_pages_visually_reviewed"] and not audit["open_blockers"]
                and audit["inputs_sha256"] == v["lock"]["inputs_sha256"],
                "REVIEW_AUDIT_STALE: " + report_id)
        result.append(report_id)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT.parents[1])
    args = parser.parse_args()
    try:
        for report_id in check(args.repo):
            print("COVERED", report_id)
    except (EvidenceError, OSError) as exc:
        parser.exit(1, "FAIL: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
