"""Run the fixed-lane device comparison under the existing Tesy host guard."""

from pathlib import Path
from runpy import run_path

if __name__ == "__main__":
    device = run_path(Path(__file__).with_name("device.py"))
    device["IO"]["main"](device["physical"])
