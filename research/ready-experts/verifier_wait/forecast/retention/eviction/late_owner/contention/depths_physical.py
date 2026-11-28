"""Enter the existing host guard for the mixed-depth NVMe fixture."""

from pathlib import Path
from runpy import run_path

if __name__ == "__main__":
    study = run_path(Path(__file__).with_name("depths.py"))
    study["IO"]["main"](study["physical"])
