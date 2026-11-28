"""Execute the router-release comparison under the frozen physical guards."""

from pathlib import Path
from runpy import run_path

if __name__ == "__main__":
    family = run_path(Path(__file__).with_name("release.py"))
    family["IO"]["main"](family["physical"])
