"""Supervise the external sampler under the existing Tesy resource and volume guard."""

from pathlib import Path
from runpy import run_path

if __name__ == "__main__":
    sample = run_path(Path(__file__).with_name("sampled.py"))
    sample["IO"]["main"](sample["physical"])
