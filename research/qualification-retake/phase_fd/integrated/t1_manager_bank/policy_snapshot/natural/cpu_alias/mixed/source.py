"""Apply audited local changes to the previously qualified mixed-scheduler fixture."""

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[6]
MIXED = QUAL / "packed_cpu_mixed"
INTEGRATED = HERE.parents[4]
NATIVE = INTEGRATED / "t1_manager_cuda/device"
DIGEST = "28fc0eafbfcb17bb9729fb17075523534366db25b303860192d711f31478a343"


def render():
    origin = (MIXED / "mixed.cpp").read_bytes()
    if hashlib.sha256(origin).hexdigest() != DIGEST:
        raise ValueError("mixed C269 reference source")
    s = origin.decode()

    def replace(old, new):
        nonlocal s
        if s.count(old) != 1:
            raise ValueError("source anchor: " + old)
        s = s.replace(old, new)

    replace("namespace mixed {", '#include "alias.h"\n\nnamespace mixed {')
    replace('const char *phase="init";', 'const char *phase="init";\n    int slot39_tag=39;')
    replace(
        "const int s=selected(n,p,r);",
        "const int physical=selected(n,p,r);\n            const int s=physical==39 ? slot39_tag : physical;",  # noqa: E501
    )
    replace(
        "Outputs graph(ggml_backend_t cpu,ggml_backend_t gpu,int n,bool packed,std::ostream &journal)",  # noqa: E501
        "std::vector<Outputs> graph(ggml_backend_t cpu,ggml_backend_t gpu,int n,bool packed,int tag,std::ostream &journal)",  # noqa: E501
    )
    replace(
        '    ggml_backend_buffer_ptr memory(ggml_backend_buft_alloc_buffer(buft,capacity+page));\n    check(memory && ggml_backend_buffer_get_type(memory.get())==buft,"CPU normal weight buffer");',  # noqa: E501
        """    std::unique_ptr<AliasArena> arena;
    if (packed) arena = std::make_unique<AliasArena>(capacity);
    ggml_backend_buffer_ptr memory(packed
        ? ggml_backend_cpu_buffer_from_ptr(arena->base(), capacity)
        : ggml_backend_buft_alloc_buffer(buft,capacity+page));
    check(memory != nullptr, "weight allocation");
    auto actual_type = ggml_backend_buffer_get_type(memory.get());
    if (packed) {
        check(std::string(ggml_backend_buft_name(actual_type))=="CPU_Mapped" &&
              ggml_backend_buft_is_host(actual_type) &&
              ggml_backend_buffer_get_base(memory.get())==arena->base(), "original mapped weights");
    } else {
        check(actual_type==buft, "ordinary dense CPU weights");
    }""",
    )
    replace(
        'packed?"packed":"dense",journal};',
        'packed?"original":(tag==39?"dense_A":"dense_B"),journal};\n    state.slot39_tag=tag;',
    )
    replace(
        "            std::memset(dst,0,slab);\n            fill(dst,k,slot);",
        """            if (packed && slot==39) continue; // immutable memfd prepared before binding
            std::memset(dst,0,slab);
            fill(dst,k,slot==39 ? tag : slot);""",
    )
    start = s.index(
        '    check(ggml_backend_sched_graph_compute(sched.get(),g)==GGML_STATUS_SUCCESS,"graph compute");'  # noqa: E501
    )
    end = s.index("\n}", start)
    s = s[:start] + (HERE / "observation.inc").read_text() + s[end:]
    start = s.index("int main(int argc,char **argv) try {")
    return s[:start] + (HERE / "main.inc").read_text()
