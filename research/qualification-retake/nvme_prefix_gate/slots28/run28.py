"""Execute only the frozen C294 slots28 diagnostic and the E12.5 pair."""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from run_pair import Profile, main  # noqa: E402

SLOTS28 = Profile(
    28,
    25 * (1024**3) // 2,
    HERE,
    HERE / "attempt-01/receipt.json",
    "67071b89a21c2836276b54fe3df07e5cd92c13723dadf5aa93f19d4b1dd7fe7e",
)

if __name__ == "__main__":
    main(SLOTS28)
