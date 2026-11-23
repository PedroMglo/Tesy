"""Verify recovery of the recorded branches from one full Git checkout."""
import json
import subprocess
import sys
from collections import defaultdict
from functools import cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def git(*args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C", ROOT, *args])


def require(value, message):
    if not value:
        raise ValueError(message)


def oid(spec):
    return git("rev-parse", "--verify", spec).decode().strip()


@cache
def leaves(tree):
    result = {}
    for record in git("ls-tree", "-r", "-z", tree).split(b"\0"):
        if record:
            meta, path = record.split(b"\t", 1)
            result[path.decode()] = tuple(meta.split())
    return result


def verify():
    manifest = json.loads((HERE / "branches.json").read_text(encoding="utf-8"))
    require(git("rev-parse", "--is-shallow-repository").strip() == b"false",
            "historical verification requires a full clone (git fetch --unshallow origin main)")
    head = oid("HEAD^{commit}")
    roots = set(git("rev-list", "--max-parents=0", head).decode().splitlines())
    require(roots == set(manifest["roots"].values()), "unrecognised roots")
    current = leaves(oid(head + "^{tree}"))
    branches = manifest["branches"]
    require(len({b["branch"] for b in branches}) == len(branches), "duplicate branch")
    variants = defaultdict(set)
    for branch in branches:
        sha, tree = branch["commit"], branch["tree"]
        git("merge-base", "--is-ancestor", sha, head)
        require(oid(sha + "^{tree}") == tree, "tree mismatch for " + branch["branch"])
        git("merge-base", "--is-ancestor", manifest["roots"][branch["lineage"]], sha)
        files = leaves(tree)
        require(len(files) == branch["files"], "file count mismatch for " + branch["branch"])
        for name, entry in files.items():
            variants[name].add(entry)

    archived = defaultdict(set)
    for prefix, sha in manifest["archived_trees"].items():
        tree = oid(sha + "^{tree}")
        require(oid(f"{head}:{prefix}") == tree, f"altered archive {prefix}")
        for name, entry in leaves(tree).items():
            archived[name].add(entry)
    for dest, record in manifest["archived_files"].items():
        name = record["path"]
        entry = leaves(oid(record["commit"] + "^{tree}"))[name]
        require(current.get(dest) == entry, f"altered archive {dest}")
        archived[name].add(entry)

    relocated = sorted(variants.keys() - current.keys())
    for name in relocated:
        require(variants[name] <= archived[name], f"historical file missing: {name}")
    return {
        "heads": len(branches), "roots": len(roots), "historical_paths": len(variants),
        "at_original_location": len(variants) - len(relocated), "archived_paths": len(relocated),
        "historical_file_versions": sum(map(len, variants.values())),
        "paths_with_multiple_versions": sum(len(v) > 1 for v in variants.values()),
        "archived_trees": len(manifest["archived_trees"]),
    }


if __name__ == "__main__":
    try:
        print(json.dumps(verify(), indent=2))
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        sys.exit(f"INCOMPLETE_HISTORY: {exc}")
