"""Generate the observer by four anchored insertions in the authenticated B3 main TU."""

import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from schema import population  # noqa: E402

PARENT = "14f6057f84f5d11908ae257e4d590ccb31c4413e96105f775e4f355c1e4712fb"


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("unexpected parent source anchor")
    return text.replace(old, new)


def render():
    raw = (HERE.parent / "native.cpp").read_bytes()
    if hashlib.sha256(raw).hexdigest() != PARENT:
        raise ValueError("source of the B3 control")
    text = raw.decode()
    table = []
    for _, name, s in population():
        d1 = s.dims[1] if len(s.dims) == 2 else 1
        args = f"{len(s.dims)},{s.dims[0]},{d1},GGML_TYPE_{s.kind},"
        table.append('{"' + name + '",{' + args + f"GGML_OP_{s.ops[0]},GGML_OP_{s.ops[-1]}" + "}}")
    header = once((HERE / "observer.inc").read_text(), "CUT_TABLE", ",\n".join(table))
    text = once(
        text,
        '#include "llama-model.h"',
        '#include "llama-model.h"\n#include "ggml-cpu.h"\n#include "ggml-alloc.h"\n#include <map>',
    )
    text = once(text, "struct Observer {", header + "\nstruct Observer {\n    Boundary boundary;")
    text = once(
        text,
        "        return false;\n    }\n};",
        "        return self.boundary.sample(tensor, ask);\n    }\n};",
    )
    text = once(
        text,
        "    observer.ffn=0;",
        "    observer.boundary.begin(step,width,out);\n    observer.ffn=0;",
    )
    text = once(
        text,
        "    check(observer.ffn==width",
        "    observer.boundary.finish();\n    check(observer.ffn==width",
    )
    text = once(
        text,
        "            check(batch_rows(3,0)",
        "            test_boundary_stride();\n            check(batch_rows(3,0)",
    )
    return text.encode()
