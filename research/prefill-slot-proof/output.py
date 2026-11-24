"""Publish one compact receipt in a fresh campaign directory."""

import json
import os


def publish(directory, calculate):
    directory.mkdir()
    try:
        result = calculate()
        pending = directory / ".pending"
        with pending.open("x", encoding="utf-8") as out:
            json.dump(result, out, indent=2, allow_nan=False)
            out.write("\n")
        os.replace(pending, directory / "receipt.json")
    except Exception as exc:
        # Keep the campaign identity and failure. Avoid copying local paths into Git.
        (directory / "FAIL.txt").write_text(type(exc).__name__ + "\n")
        raise
