"""Single 10 GiB stock startup under the project's native FILE_PAGING v3 semantics."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stock_startup"))
from start import cli  # noqa: E402

if __name__ == "__main__":
    cli(paging=True)
