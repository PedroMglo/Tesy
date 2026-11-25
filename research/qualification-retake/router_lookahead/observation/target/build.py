"""Private C291 build. Reuse the authenticated pack overlay, controls and loader closure."""

import shutil
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[2]
PACK = QUAL / "igpu_resident_rank/request_budget/device/pack_native"
BASE = run_path(str(PACK / "dso/build.py"))
PROFILE = run_path(str(PACK / "full_prefix/build.py"))
need, sha, bind = BASE["need"], BASE["sha"], PROFILE["bind"]
PARENT = {
    "llama-context.cpp": "34d6c2d2428f0f9361c5552147a2ea4252ab55f33c7fef11e551c228a52356b7",
    "llama-moe-stream.cpp": "5acbca52a8da36c300022faefac2038243ffd3f967f263873f23cec9947597ad",
    "phase-fd-integrated.h": "bc622a0ab63c8270a2701be138b64c8286f39a6e48528e02726dd48a4d93ba1a",
}
PROTOCOL = "25550111b9792e06c71f21080f0f4f2c36d78abfe8b96b04510510a146373ac7"


def replace(text, old, new):
    need(text.count(old) == 1, "ambiguous source anchor " + old[:90])
    return text.replace(old, new)


def sources(backend, directory):
    src = BASE["private_sources"](backend, directory)
    need({p.name: sha(p) for p in src.iterdir()} == PARENT, "C291 pack PFJ sources")
    # Keep the earlier real lookup probes, guarded in this variant by an independent opt-in.
    header = (HERE.parent / "lookahead.h").read_text()
    header = replace(
        header,
        "namespace lookahead {",
        """namespace lookahead __attribute__((visibility("hidden"))) {
inline bool enabled() {
    if (!pfj::active()) return false;
    static const bool flag=[]() {
        const char *v=std::getenv("TESY_ROUTER_LOOKAHEAD");
        return v && std::strcmp(v,"1")==0;
    }();
    return flag;
}""",
    )
    (src / "lookahead.h").write_text(
        header.replace("if (!pfj::active()) return;", "if (!enabled()) return;")
    )
    for name in ("profile.h", "projector.h"):
        shutil.copyfile(HERE / name, src / name)
    inc = '#include "phase-fd-integrated.h"'
    path = src / "llama-moe-stream.cpp"
    code = replace(path.read_text(), inc, inc + '\n#include "lookahead.h"')
    for pointer, indent, declaration in [
        (True, 8, "const auto it"),
        (False, 12, "const auto    it"),
    ]:
        access = "sl->" if pointer else "sl."
        text = " " * indent + f"{declaration} = {access}expert_slot.find(e);"
        guard = " " * indent + f"if (it != {access}expert_slot.end())"
        hook = f"lookahead::lookup_locked({'*sl' if pointer else 'sl'}, e, "
        hook += f"it == {access}expert_slot.end() ? -1 : it->second);"
        code = replace(code, text + "\n" + guard, text + "\n" + " " * indent + hook + "\n" + guard)
    path.write_text(code)
    path = src / "llama-context.cpp"
    code = replace(path.read_text(), inc, inc + '\n#include "profile.h"')
    call = "graph_compute(res->get_gf(), ubatch.n_tokens > 1)"
    hook = f"""auto compute_tile = [&]() {{ return {call}; }};
    const auto status = [&]() {{
        if (!lookahead::enabled()) return compute_tile();
        target_probe::Session probe{{model, ubatch, n_outputs, sched.get(),
                cparams.cb_eval, cparams.cb_eval_user_data}};
        return probe.run(compute_tile);
    }}();"""
    path.write_text(replace(code, f"const auto status = {call};", hook))
    return src


def run(a, out, r):
    need(sha(HERE / "protocol.md") == PROTOCOL and a.intact_receipt, "protocol and control")
    bind(BASE["run"], private_sources=sources)(a, out, r)
    need(r["control_sha256"] == PROFILE["CONTROL"], "recompiled control")
    need(
        all(
            "target_probe" not in x and "lookahead" not in x
            for x in r["candidate_export_changes_vs_control"]
        ),
        "probe leaked new public ABI",
    )
    r.update(
        status="PASS_C291_ROUTER_LOOKAHEAD_STATIC_C281",
        probe_protocol_sha256=PROTOCOL,
        probe_sources={k: sha(HERE / k) for k in ("build.py", "profile.h", "projector.h")},
        parent_pack_build_sha256=PROFILE["PARENT"],
        numerical_gate="NOT_RUN_MODEL_REQUIRED",
    )


if __name__ == "__main__":
    raise SystemExit(bind(BASE["main"], run=run)())
