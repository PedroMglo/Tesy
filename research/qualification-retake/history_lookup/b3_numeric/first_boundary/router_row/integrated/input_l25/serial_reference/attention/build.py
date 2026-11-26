"""Build the single added layer-25 probe using the authenticated observer and compiler command."""

import argparse
import os
import shutil
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
S = run_path(str(HERE.parent / "probe.py"))
N, need, sha, read, save = (S[k] for k in ("N", "need", "sha", "read", "save"))
METHOD = "28f7ae3b1e0a6afdba9b8a7a43e06679b9fe6a5c02a84907bbc08c9d35198598"
IMAGE = S["G"]["probes"].IMAGE_SHA
ON = "TESY_B3_ROUTER_ROW"


def render():
    src = S["G"]["probes"].render().decode()
    once = S["G"]["probes"].old.historical.once
    src = once(src, "struct Boundary {", (HERE / "mask.inc").read_text() + "\nstruct Boundary {")
    src = once(
        src,
        "    Boundary() {",
        '    Boundary() {\n        cuts.emplace("__fattn__-25", '
        'Cut{2,64,64,GGML_TYPE_F32,GGML_OP_FLASH_ATTN_EXT,GGML_OP_FLASH_ATTN_EXT});',
    )
    src = once(
        src,
        "check(l25.cuts.size()==394 &&",
        'test_attention_mask_row(); check(l25.cuts.size()==395 && '
        'l25.cuts.count("__fattn__-25")==1 &&',
    )
    old = "            auto v = copy(t, c, i);"
    mask = """            if (name == "__fattn__-25") {
                auto words = attention_mask_row(t->src[3],width,i);
                const auto filename = "mask-25-"+std::to_string(start+i)+".f16";
                const auto destination = root.parent_path()/filename;
                write_new(destination,words.data(),words.size()*sizeof(uint16_t));
            }
"""
    return once(src, old, mask + old).encode()


class Authority(N["Current"]):
    def __init__(self, static, out, elf_sha):
        super().__init__(static, capture=(out / "b3-numeric", elf_sha))
        self.search = os.pathsep.join((str(out), self.search))
        soname = S["SC"]["SONAME"]
        library = out / "libllama.so.0.0.9884"
        need(
            sha(library) == IMAGE and (out / soname).resolve(strict=True) == library,
            "integrated router DSO",
        )
        prev = self.verified["closure"][soname]["file"]
        for mapping in (self.files, self.stats, self.keys):
            del mapping[prev]
        self.files[str(library)] = IMAGE
        self.stats[str(library)] = N["AU"]["identity"](library)
        self.keys[str(library)] = N["AU"]["reference_key"](str(library), self.stats[str(library)])
        self.allowed = set(self.files)
        self.initial = (self.initial - {prev}) | {str(library)}
        self.verified = self.verified | dict(
            closure=self.verified["closure"] | {soname: dict(file=str(library), sha256=IMAGE)}
        )


def build(a, out):
    need(
        sha(HERE / "protocol.md") == METHOD and sha(a.parent / "receipt.json") == S["BUILD"],
        "source authorities",
    )
    parent = read(a.parent / "receipt.json")
    child = a.parent / "client"
    p = read(child / "receipt.json")
    need(
        sha(child / "receipt.json") == parent["client_receipt_sha256"]
        and sha(child / "command.json") == p["command_sha256"]
        and (child / "boundary.cpp").read_bytes() == S["G"]["probes"].render()
        and sha(child / "b3-numeric") == p["binary_sha256"] == S["ELF"],
        "old translation unit",
    )
    cmd = read(child / "command.json")
    compiler = Path(cmd[0])
    env = S["SC"]["OLD"]["environment"]([])
    cc1 = subprocess.check_output(
        [compiler, "-print-prog-name=cc1plus"], env=env, text=True
    ).strip()
    need(
        sha(compiler) == p["compiler_sha256"] and sha(Path(cc1)) == p["cc1plus_sha256"], "compiler"
    )
    src, dep, exe = out / "boundary.cpp", out / "headers.d", out / "b3-numeric"
    src.write_bytes(render())
    original = Path(cmd[-1]).parent
    for name, dest in (("boundary.cpp", src), ("headers.d", dep), ("b3-numeric", exe)):
        old = str(original / name)
        need(cmd.count(old) == 1, "unique compiler argument")
        cmd[cmd.index(old)] = str(dest)
    save(out / "command.json", cmd)
    with (out / "compiler.log").open("xb") as log:
        subprocess.run(cmd, env=env, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=115)
    core = run_path(str(S["QUAL"] / "history_lookup/b3_numeric/build.py"))
    cap = Path(cmd[1].split("=", 1)[1].strip('"'))
    repo = Path(cmd[cmd.index("-I") + 1]).parents[1].resolve(strict=True)
    direct = repo.parents[1] / "tools/c210_direct_reader.h"
    hdr = core["headers"](dep, repo, src, cap, direct)
    need(
        hdr == p["headers_sha256"] | {"native.cpp": sha(src)}
        and core["metadata"](exe) == core["metadata"](child / "b3-numeric"),
        "frozen headers or ELF dynamic contract",
    )
    lib = out / "libllama.so.0.0.9884"
    shutil.copyfile(a.parent / parent["candidate_file"], lib)
    lib.chmod(0o500)
    (out / S["SC"]["SONAME"]).symlink_to(lib.name)
    auth = Authority(a.static, out, sha(exe))
    environ = S["SC"]["OLD"]["environment"](auth.search.split(os.pathsep))
    for name, args in (
        ("list", [S["SC"]["OLD"]["LOADER"], "--list", exe]),
        ("relocate", ["/usr/bin/ldd", "-r", exe]),
    ):
        result = subprocess.run(args, capture_output=True, text=True, env=environ, timeout=15)
        text = result.stdout + result.stderr
        (out / (name + ".txt")).write_text(text)
        need(
            result.returncode == 0
            and "undefined symbol" not in text
            and "not found" not in text
            and {
                n: str(p.resolve(strict=True)) for n, p in S["SC"]["OLD"]["interpret"](text).items()
            }
            == {n: r["file"] for n, r in auth.verified["closure"].items()},
            "ELF " + name,
        )
    proc = subprocess.run(
        [exe, "--self-test"],
        capture_output=True,
        timeout=12,
        env=environ | {ON: "1", "CUDA_VISIBLE_DEVICES": ""},
    )
    (out / "self-test.stdout").write_bytes(proc.stdout)
    (out / "self-test.stderr").write_bytes(proc.stderr)
    need(
        proc.returncode == 0 and proc.stdout == b"PASS_B3_NUMERIC_ROW_PLAN\n",
        "395 sites and mask views",
    )
    return dict(
        status="GO_CURRENT_ATTENTION_PAIR",
        elf_sha256=sha(exe),
        source_sha256=sha(src),
        graph_sha256=IMAGE,
        previous_build_sha256=S["BUILD"],
        protocol_sha256=METHOD,
        compiler_sha256=sha(compiler),
        header_count=len(hdr),
        current_providers=auth.verified["closure"],
        model_starts=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "static", "new-output-dir"):
        p.add_argument("--" + name, required=True, type=Path)
    a = p.parse_args()
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    try:
        r = build(a, out)
    except Exception as error:
        r = dict(status="FAIL_PRESERVED", reason=f"{type(error).__name__}: {error}", model_starts=0)
    save(out / "receipt.json", r)
    print(r["status"], r.get("reason", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
