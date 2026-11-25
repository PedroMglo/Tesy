"""Compose the C266 graph and the pinned GGML operand observer."""

import hashlib


def read(path, digest):
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != digest:
        raise ValueError("unexpected pinned source " + path.name)
    return source.decode()


def between(s, first, last):
    return s[s.index(first) : s.index(last, s.index(first))]


def generate(parent, study, output):
    s = read(parent / "layer.cpp", LAYER)
    h = read(parent / "slot_witness.h", OBSERVER)
    structure = between(h, "struct Audit", 'extern "C" ssize_t __real_pread')
    observer = h[h.index("static bool observe(") :]
    observer = observer.replace(
        "ggml_backend_buffer_get_type(src->buffer)!=ggml_backend_cpu_buffer_type()",
        'std::string(ggml_backend_buft_name(ggml_backend_buffer_get_type(src->buffer)))!="CPU_Mapped"',
    ).replace(
        "        ++a.seen_ids[w];",
        "        if(w==0) alias_hold_locked(a);\n        ++a.seen_ids[w];",
    )
    header = s[: s.index("static void counterexamples()")]
    header = header.replace(
        "constexpr int width=2880,all=153,first=32,nt=32;",
        "constexpr int width=2880,all=153,nt=32; static int first=32;",
    ).replace('#include "slot_witness.h"', structure + '\n#include "real.h"\n' + observer)
    tile = between(s, "template<class T> static std::vector<T> tile(", "static json run(")
    body = between(
        s,
        "    auto ctx=context();auto *c=ctx.get();auto *g=ggml_new_graph_custom",
        "    const auto found=values<float>(out);",
    )
    setup = between(s, "    auto meta=context();", "    manager.alloc_bufs(false);")
    setup = setup.replace(
        'observed.slot_stride=mode=="DENSE"?slab:window;observed.direct=mode=="DIRECT";',
        "observed.slot_stride=window;",
    )
    setup = setup.replace("    std::copy(ids.begin(),ids.end(),observed.logical.begin());", "")
    store = between(
        s,
        "    manager.expert_store=std::make_unique",
        "    auto ctx=context();auto *c=ctx.get();auto *g=ggml_new_graph_custom",
    )
    suffix = (study / "layer.inc").read_text()
    for key, bodypart in (
        ("TILE_FUNCTION", tile),
        ("CANONICAL_GRAPH", body),
        ("ORIGINAL_REGISTRATION", setup),
        ("PINNED_STORE_INDEX", store),
    ):
        tag = "/*" + key + "*/"
        if suffix.count(tag) != 1:
            raise ValueError("missing composition site")
        suffix = suffix.replace(tag, bodypart)
    (output / "layer.cpp").write_text(header + suffix)


LAYER = "e1240b2981b49163efa9156ac9bc15f7865770f7c1016e26a8ea61ad9d97c14a"
OBSERVER = "31f6fa07cb1606efcbdee913a6982b8478bbdab405b352be2d79d779303cec90"
