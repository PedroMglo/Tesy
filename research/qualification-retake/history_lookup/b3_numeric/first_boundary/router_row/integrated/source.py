"""Materialize one private C269 graph change and derive its strictly typed callback."""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FB = HERE.parents[1]
sys.path.insert(0, str(FB))
import render as historical  # noqa: E402
from schema import SITES  # noqa: E402

Q = FB.parents[2]
STAGES = tuple(
    s
    for s in SITES
    if s.name in ("ffn_moe_logits", "ffn_moe_probs", "ffn_moe_topk", "ffn_moe_weights_softmax")
)
ON = "TESY_B3_ROUTER_ROW"
GRAPH = "d1a2ce42e649305416665091ecee4523c1638721d42cca34b51a03bbcfce3288"


def graph(source):
    old = "        logits = build_lora_mm(gate_inp, cur); // [n_expert, n_tokens]"
    new = """
        const char *row_mode = std::getenv("TESY_B3_ROUTER_ROW");
        if (arch == LLM_ARCH_OPENAI_MOE && n_tokens == 3 &&
                row_mode && std::strcmp(row_mode, "1") == 0) {
            GGML_ASSERT(loras->empty() && cur->type == GGML_TYPE_F32 &&
                        gate_inp->type == GGML_TYPE_F32);
            GGML_ASSERT(cur->ne[0]==2880 && cur->ne[1]==3 && cur->ne[2]==1 && cur->ne[3]==1);
            GGML_ASSERT(gate_inp->ne[0]==2880 && gate_inp->ne[1]==128 && n_expert_used==4);
            ggml_tensor *parts[3];
            for (int j=0;j<3;++j) {
                auto *col=ggml_view_2d(ctx0,cur,cur->ne[0],1,cur->nb[1],j*cur->nb[1]);
                parts[j]=build_lora_mm(gate_inp,col);
                GGML_ASSERT(parts[j]->op==GGML_OP_MUL_MAT && parts[j]->src[0]==gate_inp &&
                    parts[j]->src[1]==col && col->src[0]==cur && col->view_offs==j*cur->nb[1]);
            }
            logits=ggml_concat(ctx0,ggml_concat(ctx0,parts[0],parts[1],1),parts[2],1);
        } else {
            logits = build_lora_mm(gate_inp,cur);
        }"""
    return historical.once(
        historical.once(source, "#include <cassert>", "#include <cassert>\n#include <cstdlib>"),
        old,
        new,
    )


def client():
    s = historical.render().decode()
    extra = []
    for site in STAGES:
        extra.append(
            f'            cuts.emplace("{site.name}-"+std::to_string(il),cuts.at("{site.name}-0"));'
        )
    s = historical.once(
        s,
        "    std::set<std::string> observed;",
        "    Boundary() {\n        for(int il=14;il<36;++il) {\n"
        + "\n".join(extra)
        + "\n        }\n    }\n    std::set<std::string> observed;",
    )
    s = historical.once(
        s,
        "        if (t->op != c.op && t->op != c.alt) {",
        """
        const bool router = name.rfind("ffn_moe_logits-",0)==0;
        const bool split = router && width==3 && std::getenv("TESY_B3_ROUTER_ROW") &&
            std::string(std::getenv("TESY_B3_ROUTER_ROW"))=="1";
        if (split) {
            check(t->op==GGML_OP_CONCAT && t->op_params[0]==1 &&
                  t->src[0] && t->src[1] && t->src[0]->ne[1]==2 && t->src[1]->ne[1]==1,
                  "width-three reconstructed router");
        } else if (t->op != c.op && t->op != c.alt) {""",
    )
    s = historical.once(
        s,
        'std::string(argv[1])=="--self-test"',
        '(std::string(argv[1])=="--self-test" || std::string(argv[1])=="--mapping-test")',
    )
    s = historical.once(
        s,
        '            std::cout<<"PASS_B3_NUMERIC_ROW_PLAN',
        '            if (std::string(argv[1])=="--mapping-test") {\n'
        '                std::cout << "READY" << std::endl;\n'
        '                check(std::cin.get()==71,"no-model release");\n'
        '            }\n            std::cout<<"PASS_B3_NUMERIC_ROW_PLAN',
    )
    return s.encode()
