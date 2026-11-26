"""Compare stock and experimental mmap modes in an ordinary CPU Llama inference."""

import argparse
import hashlib
import json
import math
import os
import resource
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIN = "e95426f16982054c379ca7bdc8186996dd22f0fe"
VOCAB = 32
PROMPTS = ((3, 7, 9), (11, 5))
DRIVER = r"""
#include "llama.h"
#include "ggml-backend.h"
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <dlfcn.h>
#include <fstream>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
static struct stat target;
static bool watch;
static uintptr_t base;
static size_t extent;
static int cpu_mm, other_mm;

extern "C" void *mmap(void *a, size_t n, int prot, int flags, int fd, off_t off) noexcept {
    using fn = void *(*)(void*,size_t,int,int,int,off_t);
    static const fn original = (fn)dlsym(RTLD_NEXT, "mmap");
    void *p = original(a,n,prot,flags,fd,off);
    struct stat s;
    if(watch && p != MAP_FAILED && fd>=0 && fstat(fd,&s)==0 &&
       s.st_dev==target.st_dev && s.st_ino==target.st_ino) {
        base=(uintptr_t)p; extent=n;
        printf("MAP %zu %lld %d %d\n",n,(long long)off,prot,flags);
    }
    return p;
}
extern "C" int posix_madvise(void *a, size_t n, int advice) noexcept {
    using fn = int(*)(void*,size_t,int);
    static const fn original=(fn)dlsym(RTLD_NEXT,"posix_madvise");
    int ret=original(a,n,advice);
    const auto addr=(uintptr_t)a;
    if(watch && base && addr>=base && addr-base<=extent && n<=extent-(addr-base)) {
        printf("ADVICE %zu %zu %d %d\n",(size_t)(addr-base),n,advice,ret);
    }
    return ret;
}
static bool observe(ggml_tensor *t, bool ask, void*) {
    if(t->op!=GGML_OP_MUL_MAT)return false;
    if(ask)return true;
    const auto bt=t->buffer ? ggml_backend_buffer_get_type(t->buffer) : nullptr;
    const auto dev=bt ? ggml_backend_buft_get_device(bt) : nullptr;
    if(dev && ggml_backend_dev_type(dev)==GGML_BACKEND_DEVICE_TYPE_CPU)++cpu_mm;
    else ++other_mm;
    return true;
}
int main(int argc,char **argv) {
    if(argc!=3 || stat(argv[1],&target))return 2;
    Dl_info di{};
    if(!dladdr(dlsym(RTLD_DEFAULT,"llama_model_load_from_file"),&di))return 3;
    printf("LIB %s\n",di.dli_fname);
    if(!ggml_backend_dev_by_type(GGML_BACKEND_DEVICE_TYPE_CPU))return 4;
    llama_backend_init();
    auto mp=llama_model_default_params();
    ggml_backend_dev_t devices[]={nullptr};
    mp.devices=devices; mp.n_gpu_layers=0; mp.use_extra_bufts=false; mp.no_host=true;
    mp.load_mode=LLAMA_LOAD_MODE_MMAP;
    watch=true;
    auto *model=llama_model_load_from_file(argv[1],mp);
    watch=false;
    if(!model)return 25;
    if(llama_vocab_n_tokens(llama_model_get_vocab(model))!=32)return 5;
    std::ofstream out(argv[2],std::ios::binary);
    for(int pass=0;pass<2;++pass) {
        auto cp=llama_context_default_params();
        cp.n_ctx=64; cp.n_batch=8; cp.n_ubatch=8; cp.n_threads=1; cp.n_threads_batch=1;
        cp.offload_kqv=false; cp.op_offload=false; cp.cb_eval=observe;
        auto *ctx=llama_init_from_model(model,cp);
        if(!ctx)return 6;
        llama_token a[]={3,7,9}, b[]={11,5};
        auto batch=llama_batch_get_one(pass?b:a,pass?2:3);
        if(llama_decode(ctx,batch))return 7;
        auto *logits=llama_get_logits_ith(ctx,-1);
        if(!logits)return 8;
        out.write((const char *)logits,32*sizeof(float));
        llama_free(ctx);
    }
    out.close();
    printf("CPU_MATMUL %d %d\n",cpu_mm,other_mm);
    std::ifstream maps("/proc/self/maps"); std::string line;
    while(std::getline(maps,line)) {
        auto p=line.find("/"); if(p==std::string::npos)continue;
        auto name=line.substr(p);
        if(name.find("/libllama.so")!=std::string::npos || name.find("/libggml")!=std::string::npos)
            printf("ELF %s\n",name.c_str());
    }
    llama_model_free(model); llama_backend_free();
    return out && cpu_mm>0 && other_mm==0 ? 0:9;
}
"""


def need(ok, why):
    if not ok:
        raise ValueError(why)


def digest(path):
    with path.open("rb") as h:
        return hashlib.file_digest(h, "sha256").hexdigest()


def make_model(source, path):
    sys.path.insert(0, str(source / "gguf-py"))
    import gguf
    import numpy as np

    need(
        Path(gguf.__file__).resolve().is_relative_to((source / "gguf-py").resolve()),
        "wrong GGUF writer",
    )
    w = gguf.GGUFWriter(path, "llama")
    w.add_name("Tesy deterministic CPU mmap fixture")
    w.add_file_type(0)
    w.add_context_length(64)
    w.add_embedding_length(32)
    w.add_block_count(1)
    w.add_feed_forward_length(64)
    w.add_head_count(2)
    w.add_head_count_kv(2)
    w.add_rope_dimension_count(16)
    w.add_layer_norm_rms_eps(1e-5)
    w.add_vocab_size(VOCAB)
    w.add_tokenizer_model("none")
    shapes = {
        "token_embd": (32, 32),
        "output_norm": (32,),
        "output": (32, 32),
        "blk.0.attn_norm": (32,),
        "blk.0.ffn_norm": (32,),
        **{"blk.0.attn_" + k: (32, 32) for k in ("q", "k", "v", "output")},
        "blk.0.ffn_gate": (64, 32),
        "blk.0.ffn_up": (64, 32),
        "blk.0.ffn_down": (32, 64),
    }
    for i, (name, shape) in enumerate(shapes.items(), 1):
        t = np.arange(math.prod(shape), dtype=np.int64)
        a = (((t * 37 + i * 19 + (t * t % 101)) % 251) - 125).astype(np.float32) / 512
        if len(shape) == 1:
            a += 1
        w.add_tensor(name + ".weight", a.reshape(shape))
    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_tensors_to_file()
    w.close()
    need(0 < path.stat().st_size <= 2 << 20, "GGUF size")


def mapped(text, size, lazy):
    maps, hints = [], []
    for line in text.splitlines():
        fields = line.split()
        if fields[:1] == ["MAP"]:
            maps.append(tuple(map(int, fields[1:])))
        elif fields[:1] == ["ADVICE"]:
            hints.append(tuple(map(int, fields[1:])))
    # Linux 4K posix MAP_SHARED, PROT_READ, MAP_POPULATE and POSIX_MADV_WILLNEED.
    need(
        len(maps) == 1
        and maps[0][:3] == (size, 0, 1)
        and maps[0][3] & 1
        and bool(maps[0][3] & 0x8000) != lazy,
        "target mapping flags or identity",
    )
    need([h for h in hints if h[2] == 3] == ([] if lazy else [(0, size, 3, 0)]), "target WILLNEED")
    return {"maps": maps, "advice": hints}


def outputs(b):
    need(len(b) == 2 * VOCAB * 4, "full logits size")
    ids = []
    for row in struct.iter_unpack("<32f", b):
        need(
            all(math.isfinite(x) for x in row) and max(row) > min(row),
            "non-finite or constant logits",
        )
        ids.append(row.index(max(row)))
    need(b[:128] != b[128:], "indistinguishable probe rows")
    return ids


def bounded():
    resource.setrlimit(resource.RLIMIT_AS, (768 << 20, 768 << 20))


def check_run(stock, overlay, out, receipt):
    src = stock / "source"
    libs = stock / "build/bin"
    manifest = json.loads((overlay / "receipt.json").read_bytes())
    need(manifest["status"] == "PASS_PRIVATE_GOLD_AND_CANDIDATE_BUILD", "build control")
    ref = libs / "libllama.so.0.9.0"
    cand = (overlay / "candidate/libllama.so.0").resolve()
    need(
        digest(ref) == manifest["original_sha256"] == manifest["phases"]["gold"]["sha256"]
        and digest(cand) == manifest["phases"]["candidate"]["sha256"],
        "build ELF mismatch",
    )
    need(
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=src, text=True).strip() == PIN
        and not subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=src, text=True
        ).strip(),
        "stock pin or dirty source",
    )
    model = out / "tiny.gguf"
    make_model(src, model)
    receipt.update(
        gguf_sha256=digest(model),
        gguf_bytes=model.stat().st_size,
        overlay_receipt_sha256=digest(overlay / "receipt.json"),
        prompts=PROMPTS,
    )
    cpp = out / "probe.cpp"
    cpp.write_text(DRIVER)
    exe = out / "probe"
    cc = [
        "/usr/bin/g++",
        "-std=c++17",
        "-O2",
        "-fPIC",
        "-pie",
        "-fno-plt",
        "-rdynamic",
        "-I" + str(src / "include"),
        "-I" + str(src / "ggml/include"),
        str(cpp),
        "-L" + str(libs),
        "-Wl,-rpath-link," + str(libs),
        "-lllama",
        "-lggml",
        "-lggml-base",
        "-ldl",
        "-o",
        str(exe),
    ]
    subprocess.run(cc, check=True, timeout=90, capture_output=True)
    receipt.update(compiler_sha256=digest(Path(cc[0])), probe_sha256=digest(exe), arms={})
    reference = None
    for mode, value in (("stock", None), ("OFF", "0"), ("ON", "1"), ("invalid", "invalid")):
        expected = (ref if mode == "stock" else cand).resolve()
        root = out / mode
        root.mkdir()
        env = {
            **os.environ,
            "CUDA_VISIBLE_DEVICES": "",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "LD_LIBRARY_PATH": str(expected.parent) + ":" + str(libs),
        }
        env.pop("LD_PRELOAD", None)
        env.pop("TESY_STOCK_LAZY_MMAP", None)
        if value is not None:
            env["TESY_STOCK_LAZY_MMAP"] = value
        proc = subprocess.run(
            [str(exe), str(model), str(root / "logits.f32")],
            env=env,
            preexec_fn=bounded,
            timeout=90,
            capture_output=True,
        )
        (root / "stdout").write_bytes(proc.stdout)
        (root / "stderr").write_bytes(proc.stderr)
        log = proc.stdout.decode()
        arm = {
            "exit": proc.returncode,
            "stdout_sha256": digest(root / "stdout"),
            "stderr_sha256": digest(root / "stderr"),
        }
        receipt["arms"][mode] = arm
        need(
            [Path(line[4:]).resolve() for line in log.splitlines() if line.startswith("LIB ")]
            == [expected],
            "loader ELF identity " + mode,
        )
        if mode == "invalid":
            need(
                proc.returncode == 25
                and not (root / "logits.f32").exists()
                and b"TESY_STOCK_LAZY_MMAP" in proc.stderr,
                "invalid option accepted or unrelated error",
            )
            continue
        need(proc.returncode == 0, "CPU loader or decoder failed: " + mode)
        arm.update(mapped(log, model.stat().st_size(), mode == "ON"))
        elf = {Path(line[4:]).resolve() for line in log.splitlines() if line.startswith("ELF ")}
        expected_elf = {expected} | {
            (libs / name).resolve() for name in manifest["stock_dsos"] if name.startswith("libggml")
        }
        need(
            elf == expected_elf
            and all(
                digest(libs / name) == sha
                for name, sha in manifest["stock_dsos"].items()
                if name.startswith("libggml")
            ),
            "mapped GGML/llama ELF set",
        )
        mm = [line.split() for line in log.splitlines() if line.startswith("CPU_MATMUL ")]
        need(len(mm) == 1 and int(mm[0][1]) > 0 and int(mm[0][2]) == 0, "CPU compute proof")
        arm.update(
            cpu_matmuls=int(mm[0][1]), mapped_elf_sha256={p.name: digest(p) for p in sorted(elf)}
        )
        b = (root / "logits.f32").read_bytes()
        arm.update(
            greedy_ids=outputs(b), logits_sha256=hashlib.sha256(b).hexdigest(), logits_compared=64
        )
        if reference is None:
            reference = b
        need(b == reference, "stock/candidate full logits mismatch")
    return "PASS_TINY_CPU_INFERENCE_AND_MMAP"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-build-root", type=Path, required=True)
    parser.add_argument("--overlay-root", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    dest = args.new_output_dir.resolve()
    need(
        not any(
            dest.is_relative_to(p.resolve()) for p in (args.stock_build_root, args.overlay_root)
        ),
        "output overlaps source or build",
    )
    dest.mkdir(mode=0o700)
    r = {}
    try:

        def git(*cmd):
            return subprocess.check_output(
                ["git", "-c", "core.preloadIndex=false", "-c", "index.threads=1", *cmd],
                cwd=HERE,
                text=True,
            ).strip()

        r.update(
            commit=git("rev-parse", "HEAD"),
            tree=git("rev-parse", "HEAD^{tree}"),
            clean=not git("status", "--porcelain=v1", "--untracked-files=normal"),
            program_sha256=digest(Path(__file__)),
            protocol_sha256=digest(HERE / "protocol.md"),
            stock_pin=PIN,
            cap_bytes=768 << 20,
            timeout_s_per_arm=90,
        )
        need(r["clean"], "dirty measurement checkout")
        r["status"] = check_run(
            args.stock_build_root.resolve(), args.overlay_root.resolve(), dest, r
        )
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        subprocess.SubprocessError,
        ImportError,
    ) as exc:
        r.update(status="FAIL_PRESERVED", error=str(exc))
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            (dest / "failed-command.stderr").write_bytes(exc.stderr)
    tmp = dest / ".pending"
    with tmp.open("x") as f:
        f.write(json.dumps(r, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.rename(dest / "receipt.json")
    print(r["status"])
    return int(r["status"] != "PASS_TINY_CPU_INFERENCE_AND_MMAP")


if __name__ == "__main__":
    sys.exit(main())
