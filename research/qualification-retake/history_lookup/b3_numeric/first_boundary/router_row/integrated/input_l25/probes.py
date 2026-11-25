"""The eleven extra observations on the frozen ON client's already validated callback."""

import hashlib
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
BUILD_SHA = "59b721ea443dc895c830d95f2d1c6e995461de231183ffac98747c6655e3e030"
IMAGE_SHA = "294cc4ed4683a01455fd010550330808be12d9ebfdc824c8450642f93cc0db5d"
FAMILY_SHA = "27b97866f3d452786860f42133ffb247a9f06d95c904473aa2b09533de16c086"
PROTOCOL = "7f7511015ed5923b5ea27c7fa58cd51fbd377546c9ded1b2e702c8983a09ff4e"
EXTRA = {
    24: ("attn_post_norm", "ffn_moe_out", "l_out"),
    25: (
        "attn_norm",
        "Qcur",
        "Kcur",
        "Vcur",
        "attn_out",
        "ffn_inp",
        "attn_post_norm",
        "ffn_moe_out",
    ),
}
GOLD = ("attn_post_norm", "ffn_moe_out")


def load(path, label):
    spec = importlib.util.spec_from_file_location(label, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


engine = load(PARENT / "build.py", "qualified_integrated_graph")
old = engine.source


def sites():
    by_name = {s.name: s for _, _, s in old.historical.population()}
    return [(il, f"{name}-{il}", by_name[name]) for il, names in EXTRA.items() for name in names]


def render():
    source = old.client().decode()
    anchor = "    Boundary() {"
    additions = [
        f'        cuts.emplace("{name}",cuts.at("{site.name}-0"));' for _, name, site in sites()
    ]
    source = old.historical.once(source, anchor, anchor + "\n" + "\n".join(additions))
    expressions = [f'l25.cuts.count("{name}")==1' for _, name, _ in sites()]
    check = "Boundary l25; check(l25.cuts.size()==394 && " + " && ".join(expressions)
    check += ', "observer names and total cuts");'
    return old.historical.once(
        source,
        "            test_boundary_stride();",
        "            " + check + "\n            test_boundary_stride();",
    ).encode()
