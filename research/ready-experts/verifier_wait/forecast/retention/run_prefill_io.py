"""Run the two-call prefill reader with the same model, pack, and system resource gates."""

from pathlib import Path
from runpy import run_path

if __name__ == "__main__":
    family = run_path(Path(__file__).with_name("prefill_io.py"))
    family["IO"]["main"](family["physical"])
