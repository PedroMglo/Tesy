from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_REPOSITORY_REFERENCES = (
    "PedroMglo/ai-local-runtime-kit",
)

FORBIDDEN_CONTAINER_FILES = {
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    ".devcontainer/devcontainer.json",
}

IGNORED_PARTS = {
    ".git",
    ".venv",
    ".deps",
    "__pycache__",
    ".pytest_cache",
}


def _tracked_source_candidates() -> list[Path]:
    candidates: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        candidates.append(path)
    return candidates


def test_no_unapproved_cross_repo_dependency_reference() -> None:
    failures: list[str] = []
    for path in _tracked_source_candidates():
        # The archived trees retain byte-identical copies of this negative test.
        relative = path.relative_to(ROOT)
        copied_test = (
            relative.parts[:2] == ("archive", "prototypes")
            and relative.parts[3:] == ("tests", "test_repository_boundaries.py")
            and len(relative.parts) == 5
        )
        if path == Path(__file__) or copied_test:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for forbidden in FORBIDDEN_REPOSITORY_REFERENCES:
            if forbidden in text:
                failures.append(f"{path.relative_to(ROOT)} -> {forbidden}")
    assert not failures, (
        "unapproved cross-repository references: " + ", ".join(failures)
    )


def test_no_container_definition_without_explicit_adr() -> None:
    present = [
        str(path.relative_to(ROOT))
        for path in _tracked_source_candidates()
        if str(path.relative_to(ROOT)) in FORBIDDEN_CONTAINER_FILES
    ]
    assert not present, (
        "container definition requires an explicit Tesy ADR before introduction: "
        + ", ".join(present)
    )
