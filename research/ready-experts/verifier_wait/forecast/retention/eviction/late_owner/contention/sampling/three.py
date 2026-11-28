"""Evaluate both remaining three-reader classes under the independently frozen protocol."""

import sys
from functools import partial
from pathlib import Path
from runpy import run_path

if __name__ == "__main__":
    sampler = run_path(Path(__file__).with_name("sampled.py"))
    if sys.argv[1:2] == ["physical"]:
        del sys.argv[1]
        sampler["IO"]["main"](partial(sampler["physical"], triples=True))
    else:
        sampler["main"](triples=True)
