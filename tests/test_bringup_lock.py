import fcntl
import subprocess
from pathlib import Path


def test_reference_bringup_rejects_concurrent_runner(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    lock_path = root / ".deps" / "reference-bringup.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    output = tmp_path / "attempt"

    with lock_path.open("w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        completed = subprocess.run(
            [
                "bash",
                str(root / "scripts" / "run_reference_bringup.sh"),
                "missing.gguf",
                str(output),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    assert completed.returncode == 1
    assert "FAIL_CONCURRENT_BRINGUP" in completed.stderr
    assert "FAIL_CONCURRENT_BRINGUP" in (output / "failure.txt").read_text()
    assert not (output / "tesy-head.txt").exists()
