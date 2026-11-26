"""Rebind each ordered projection to a file-backed role with the same compiled shader."""

import argparse
import os
import shutil
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
STOCK = HERE.parent / "radv"
B = run_path(STOCK / "build.py")
BASE = B["BASE"]
sha, need, save, rep = [B[k] for k in ("sha", "need", "save", "replace")]
PROTO = "f9b7551620d86a9a2465a9e92f4b3f6e6c71d68ab5e18c41779f9a6d7f7b38c2"
ORDERED_SPV = "06d3fba12dceaf1d22cde8672aca70a445dd1a9fc2b2bb633d20ed868193fba8"
RHS_SPV = "a988ec4090dca42f89a13de2ce43a69c376a0e79919e6f56875d4b1e0ab1ad25"
STOCK_BUILD = "65a34219018b3e856ed18bebf9d3fe03b0ec5a8d5ed9cfd0b28bc50fc615d58e"
ORDERED_BUILD = "9a6b01afd0a80b8c5f7096de5806642e601ad5cfe3d698d675d3899590bbf9c3"


def pins():
    need(sha(HERE / "protocol.md") == PROTO, "new protocol")
    need(
        sha(STOCK / "projection.inc")
        == "f27dd604224f96ff345cb526808670cfa5b6df82dc84c53403ebfbd532035750",
        "stock implementation",
    )
    return dict(
        stock_source=B["pin"](),
        sources={n: sha(HERE / n) for n in ("protocol.md", "build.py", "backing.inc", "run.py")},
        ordered_spv=ORDERED_SPV,
        rhs_spv=RHS_SPV,
    )


def generate(out):
    B["prepare_native"](out)
    src = (STOCK / "projection.inc").read_text()
    a, b = src.index("void load_weight("), src.index("void project(")
    src = src[:a] + '#include "backing.inc"\n\n' + src[b:]
    a, b = src.index("    auto weight=getbuf("), src.index("    auto spv=words(")
    src = (
        src[:a]
        + """    SlotPool cache(p,args[5]);
    auto ids=getbuf(16),dst=getbuf(line_bytes);
"""
        + src[b:]
    )
    src = rep(
        src,
        "    VkDescriptorPoolSize ps",
        """    auto emit=[&](int role,const char *target) {
    const uint32_t local[4]{0,0,0,0};
    std::memcpy(ids.p,local,sizeof(local));std::memset(dst.p,0xff,dst.bytes);
    VkDescriptorPoolSize ps""",
    )
    src = rep(src, "{weight.b,0,matrix_bytes*slot_count}", "cache.view(role)")
    a, b = src.index("    for(unsigned i=0;i<2;++i)"), src.index("        vk(vkQueueSubmit")
    src = src[:a] + src[b:]
    src = rep(
        src,
        "        vk(vkWaitForFences(p.dev",
        """        if(cache.record->generation==6 && role==0) {
            need(!cache.publish(records[1]),"replacement while leased");
            std::puts("blocked_replacement\\t6\\t7");
        }
        vk(vkWaitForFences(p.dev""",
    )
    src = rep(src, "ids.p,physical,sizeof(physical)", "ids.p,local,sizeof(local)")
    src = rep(src, 'args[7+i],"wbx"', 'target,"wbx"')
    a, b = src.index('        std::printf("projection'), src.index("    vkDestroyFence")
    src = (
        src[:a]
        + """        std::printf("role_result\\t%d\\t%d\\t%d\\t%lu\\t%zu\\t0\\t%u\\n",
            cache.record->expert,cache.record->generation,role,(unsigned long)cache.st.st_ino,
            role*rank_bytes,line_bytes);
"""
        + src[b:]
    )
    src = rep(
        src,
        "    vkDestroyPipeline(p.dev,pipeline",
        """    };
    need(cache.publish(records[0]) && cache.acquire(3,6),"e28 lease");
    emit(0,args[7]);emit(2,args[8]);cache.release();
    need(cache.publish(records[1]) && !cache.acquire(3,6),"stale lease rejected");
    std::puts("stale_rejected\\t3\\t6\\t7");
    need(cache.acquire(3,7),"new e24 lease");emit(0,args[9]);cache.release();cache.cleanup();
    vkDestroyPipeline(p.dev,pipeline""",
    )
    src = rep(src, "{weight,ids,dst}", "{ids,dst}")
    (out / "projection.inc").write_text(src)
    path = out / "dispatch.cpp"
    path.write_text(
        rep(
            rep(path.read_text(), "argc==9", "argc==10"),
            "PASS_RADV_PROJECTION_DISPATCH",
            "PASS_RANK_BACKING_DISPATCH",
        )
    )


def build(a, out):
    need(
        all(sha(a.headers / "vulkan" / n) == h for n, h in B["HEADERS"].items()), "Khronos include"
    )
    need(
        sha(a.ordered_dir / "receipt.json") == ORDERED_BUILD
        and sha(a.stock_dir / "receipt.json") == STOCK_BUILD,
        "input builds",
    )
    need(
        sha(a.ordered_dir / "gate.spv") == ORDERED_SPV
        and sha(a.stock_dir / "subgroup.spv") == RHS_SPV,
        "original modules",
    )
    generate(out)
    for source, dest in (
        (a.ordered_dir / "gate.spv", "gate.spv"),
        (a.stock_dir / "subgroup.spv", "subgroup.spv"),
        (a.stock_dir / "shared.spv", "shared.spv"),
    ):
        shutil.copyfile(source, out / dest)
    args = [
        str(BASE["CXX"]),
        "-std=c++17",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-Wno-missing-field-initializers",
        "-I",
        str(a.headers),
        "-I",
        str(HERE),
        "-I",
        str(STOCK),
        "-I",
        str(out),
        str(out / "dispatch.cpp"),
        str(BASE["LOADER"]),
        str(B["CRYPTO"]),
        "-o",
        str(out / "rank"),
    ]
    with (out / "build.log").open("xb") as log:
        subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=30)
    return dict(
        status="PASS_RANK_BACKING_BUILD_ONLY",
        stock_build=STOCK_BUILD,
        ordered_build=ORDERED_BUILD,
        files={p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()},
        gpu_processes=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("stock-dir", "ordered-dir", "headers", "new-output-dir"):
        p.add_argument("--" + key, type=lambda s: Path(s).resolve(), required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir()
    try:
        inputs = pins()
        row = build(a, out)
        row["inputs"] = inputs
    except Exception as e:
        row = dict(status="FAIL_PRESERVED", reason=str(e))
    save(out / "receipt.json", row)
    print(row["status"], row.get("reason", ""))
    raise SystemExit(int(row["status"] == "FAIL_PRESERVED"))
