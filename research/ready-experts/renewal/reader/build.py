"""Build against the matching Fedora liburing headers extracted only for this fixture."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = "ecb5a26cc02015b01c229646f3b9927497cd54ebbe73c34f33062d3c50317405"


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def version():
    def git(*args):
        return subprocess.check_output(["git", "-C", HERE, *args], text=True).strip()

    if git("status", "--porcelain"):
        raise ValueError("working tree is not clean")
    return git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")


def build(a):
    commit, tree = version()
    if sha(a.rpm) != PACKAGE:
        raise ValueError("wrong development package")
    subprocess.run(["rpmkeys", "--checksig", a.rpm], check=True)
    dest = a.new_output_dir
    content = subprocess.check_output(["rpm2cpio", a.rpm], timeout=10)
    subprocess.run(
        ["cpio", "-idm", "--quiet", "./usr/include/*"], input=content, cwd=dest, check=True
    )
    exe = dest / "reader"
    cmd = [
        "/usr/bin/g++",
        "-std=c++20",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-pthread",
        "-I",
        str(dest / "usr/include"),
        str(HERE / "native.cpp"),
        "-l:liburing.so.2",
        "-lcrypto",
        "-o",
        str(exe),
    ]
    with (dest / "compiler.log").open("x") as log:
        subprocess.run(cmd, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=45)
    ldd = subprocess.check_output(["ldd", exe], text=True, timeout=5)
    (dest / "ldd.txt").write_text(ldd)
    paths = re.findall(r"(/\S+) \(0x", ldd)
    libs = {p: sha(p) for p in paths}
    if "not found" in ldd or not any("liburing.so.2" in p for p in libs):
        raise ValueError("missing runtime library")
    return {
        "status": "PASS",
        "commit": commit,
        "tree": tree,
        "rpm_sha256": PACKAGE,
        "compiler_sha256": sha(cmd[0]),
        "command": cmd,
        "libraries": libs,
        "native_sha256": sha(HERE / "native.cpp"),
        "elf_sha256": sha(exe),
        "sources": {p.name: sha(p) for p in HERE.iterdir() if p.suffix in {".py", ".md", ".cpp"}},
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rpm", type=Path, required=True)
    p.add_argument("--new-output-dir", type=lambda s: Path(s).resolve(), required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = build(a)
    except (ValueError, OSError, subprocess.SubprocessError) as e:
        result = {"status": "FAIL", "reason": str(e)}
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(result["status"], result.get("reason", ""))
    raise SystemExit(result["status"] != "PASS")
