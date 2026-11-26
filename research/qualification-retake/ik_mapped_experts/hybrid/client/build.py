"""Link the tiny client against one sealed ik DSO pair (ordinary C++, no CUDA compilation)."""

import argparse
import json
import re
import subprocess
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent
TINY=run_path(str(HERE.parents[1]/"tiny_loader/run.py"))
FRONT=TINY["FRONT"]
sha,need,pin=FRONT["sha"], FRONT["need"], FRONT["pinned"]
TOOLKIT=Path("/usr/local/cuda-13.3/include")
LIBS=tuple(TINY["BASE"])
GOLD="3771d5de5067095852a0132324c16b01e39c2b999082d4a3b6165e13aff90644"
TINY_SHA="b10222365dec972020668e3e9a9874018f8af2a7170ddef2c9f97ff60018cd92"


def imported(lib):
    text=subprocess.check_output(["/usr/bin/nm","-Du", lib],text=True)
    return sorted({m[1].split("@")[0] for m in re.finditer(r"\bU (cuda(?:Memcpy|HostRegister)\S*)",text)})


def build(a,out,r):
    src=a.source.resolve()
    obj=a.objects.resolve()
    def git(*args):
        return subprocess.check_output(["git","-C",src,*args],text=True).strip()
    need((git("rev-parse","HEAD"),git("rev-parse","HEAD^{tree}"))==(FRONT["PIN"],FRONT["TREE"]) and not git("status","--porcelain"),"ik source pin")
    if a.variant=="cpu":
        libs=TINY["BASE"]
        need(not a.dso_build and not a.dso_sha256,"CPU build authority")
    else:
        need(a.dso_build and a.dso_sha256,"CUDA build authority")
        b=json.loads(pin(a.dso_build/"receipt.json",a.dso_sha256).read_bytes())
        need(b["status"]=="PASS_IK_SM89_LINK_ONLY" and obj==(a.dso_build/"objects").resolve(),"CUDA build")
        libs={name:b["libraries"]["objects/"+name] for name in LIBS}
    for name in LIBS:
        pin(obj/name,libs[name])
    source={name:sha(HERE/name) for name in ("client.cpp","hooks.hpp","copy.cpp","build.py","grade.py","protocol.md")}
    for f in ("tiny_loader/probe.cpp","cpu_numeric/vma/inspect.hpp","hybrid/protocol.md"):
        source[f]=sha(HERE.parents[1]/f)
    elf=out/"hybrid-client"
    cmd=["/usr/bin/g++-15","-std=c++17","-O1","-pthread","-rdynamic","-fPIC","-pie","-fno-plt",
         *(f"-I{src/p}" for p in ("include","ggml/include","ggml/src")),f"-I{TOOLKIT}",
         str(HERE/"client.cpp"),str(HERE/"copy.cpp"),*(str(obj/name) for name in LIBS),
         "-ldl","-o",str(elf)]
    r.update(compile_argv=cmd,compiler_sha256=sha(Path(cmd[0]).resolve()),sources=source,ik_commit=git("rev-parse","HEAD"),
             libraries=libs,variant=a.variant,dso_build_sha256=a.dso_sha256,
             runtime_header_sha256=sha(TOOLKIT/"cuda_runtime_api.h"),model_starts=0)
    with (out/"compiler.log").open("xb") as f:
        subprocess.run(cmd,check=True,stdout=f,stderr=subprocess.STDOUT,timeout=60)
    r["binary_sha256"]=sha(elf)
    if a.variant=="cpu":
        r["closure"]=FRONT["closure"](elf,obj)
    else:
        imports=imported(obj/LIBS[1])
        supported={"cudaMemcpy","cudaMemcpyAsync","cudaMemcpy2D","cudaMemcpy2DAsync","cudaHostRegister",
                   "cudaMemcpyPeerAsync","cudaMemcpy3DPeerAsync"}
        need({"cudaMemcpyAsync","cudaHostRegister"}<=set(imports) and set(imports)<=supported,
             "unexpected or missing dynamically interposable CUDA copy/register imports")
        r["cuda_imports"]=imports
    return "PASS_TINY_HYBRID_CLIENT_BUILD"


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("source","objects","new-output-dir"):
        p.add_argument("--"+k,type=Path,required=True)
    p.add_argument("--variant",choices=("cpu","cuda"),required=True)
    p.add_argument("--dso-build",type=Path)
    p.add_argument("--dso-sha256")
    a=p.parse_args()
    out=a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    r={}
    try:
        r["status"]=build(a,out,r)
    except Exception as exc:
        r.update(status="FAIL_PRESERVED",error=str(exc))
    (out/"receipt.json").write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print(r["status"])
    return int(r["status"]=="FAIL_PRESERVED")

if __name__=="__main__":
    raise SystemExit(main())
