"""Reproduce the C305 shared-library link privately with the 166 sealed input objects."""

import argparse
import hashlib
import json
import os
import re
import resource
import shlex
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
C317 = "1c7ba3b67377bf22af2280f6dfa1d09fae0f1deff70bbddfa7061ecc6d9eb4ac"
DSO = "libllama.so.0.0.9884"
LINK = "d665df498b7dc4cef67184f71f9a22fa865ffda42846b7343964cd91700cbe71"
OBJECTS = "ec70d3ef4ece5490265334d82d9b713730c1cbcb29bafce1a1c079645d4f9115"
LIMIT = 200 * 2**20


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(*args, **kwargs):
    return subprocess.check_output(
        args, timeout=15, env={"PATH": "/usr/bin", "LC_ALL": "C"}, **kwargs
    )


def limits():
    resource.setrlimit(resource.RLIMIT_AS, (1280 * 2**20,) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMIT,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def interface(path, root, label):
    header = run("readelf", "-h", path).decode()
    dynamic = run("readelf", "-d", path).decode()
    notes = run("readelf", "-n", path).decode()
    symbols = run("nm", "-D", "--defined-only", "--format=posix", path)
    (root / f"{label}.dynsyms").write_bytes(symbols)
    return {
        "sha256": sha(path),
        "bytes": path.stat().st_size,
        "elf": dict(re.findall(r"^\s*(Class|Machine):\s*(.+)$", header, re.M)),
        "build_id": re.search(r"Build ID: (\w+)", notes)[1],
        "soname": re.findall(r"\(SONAME\).*?\[(.*?)\]", dynamic),
        "needed": re.findall(r"\(NEEDED\).*?\[(.*?)\]", dynamic),
        "runpath_sha256": digest(re.search(r"\(RUNPATH\).*?\[(.*?)\]", dynamic)[1].encode()),
        "dynsyms_sha256": digest(symbols),
        "dynsyms_count": len(symbols.splitlines()),
    }


def test(build, protocol, root, exploratory, receipt):
    require(sha(protocol) == C317, "C317 protocol identity")
    pins = json.loads(protocol.read_text())["file_sha256"]
    selected = {}
    for path, expected in pins.items():
        f = Path(path)
        if f.name.startswith("libggml") or f.name in ("expert-learned-staging", DSO):
            require(sha(f) == expected and f.name not in selected, "C317 binary/library identity")
            selected[f.name] = expected
    require(len(selected) == 6, "C317 client and five shared libraries")
    source = build / "llama"
    original = build / "bin" / DSO
    require(sha(original) == selected[DSO], "original ELF")
    layout = Path("CMakeFiles/llama.dir")
    command = source / layout / "link.txt"
    require(sha(command) == LINK, "pinned link command")
    receipt["source"] = {
        "commit": run("git", "-C", HERE, "rev-parse", "HEAD").decode().strip(),
        "tree": run("git", "-C", HERE, "rev-parse", "HEAD^{tree}").decode().strip(),
        "clean": not run("git", "-C", HERE, "status", "--porcelain"),
        "exploratory": exploratory,
        "script_sha256": sha(Path(__file__)),
        "preregistration_sha256": sha(HERE / "protocolo.md"),
        "c317_protocol_sha256": C317,
        "c317_libraries_and_client": selected,
        "link_command_sha256": LINK,
        "flags_make_sha256": sha(source / layout / "flags.make"),
    }
    require(exploratory or receipt["source"]["clean"], "clean source required for confirmation")

    argv = shlex.split(command.read_text())
    require(argv[0] == "/usr/bin/c++", "link driver")
    objects = [arg for arg in argv if arg.endswith(".o")]
    require(len(objects) == len(set(objects)) == 166, "expected 166 unique objects")
    # The command digest pins both write options. A mirror working directory
    # redirects ../bin/$DSO and CMakeFiles/llama.dir/link.d without editing argv.
    require(argv[argv.index("-o") + 1] == "../bin/" + DSO, "relative ELF destination")
    require("-Wl,--dependency-file=CMakeFiles/llama.dir/link.d" in argv, "relative link metadata")
    work = root / "llama"
    work.mkdir()
    (root / "bin").mkdir()
    temp = root / "tmp"
    temp.mkdir()
    rows = []
    total = 0
    for name in objects:
        rel = Path(name)
        require(rel.is_relative_to(layout) and ".." not in rel.parts, "unsafe object path")
        src, dst = source / rel, work / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        h = sha(src)
        require(sha(dst) == h, "object copy")
        rows.append(f"{h}  {name}\n")
        total += src.stat().st_size
    inventory = "".join(rows).encode()
    require(digest(inventory) == OBJECTS and total == 9_090_808, "sealed object set/order")
    (root / "objects.sha256").write_bytes(inventory)
    receipt["objects"] = {"count": len(rows), "bytes": total, "manifest_sha256": OBJECTS}
    receipt["toolchain"] = {}
    for name in ("c++", "ld", "readelf", "nm"):
        tool = Path("/usr/bin") / name
        receipt["toolchain"][name] = {
            "sha256": sha(tool),
            "version": run(tool, "--version").decode().splitlines()[0],
        }
    receipt["original"] = interface(original, root, "original")
    receipt["link_invocations"] = 1
    with (root / "link.out").open("xb") as out, (root / "link.err").open("xb") as err:
        proc = subprocess.run(
            argv,
            cwd=work,
            stdout=out,
            stderr=err,
            env={"PATH": "/usr/bin", "LC_ALL": "C", "TMPDIR": str(temp), "HOME": str(root)},
            timeout=90,
            preexec_fn=limits,
        )
    receipt["link_returncode"] = proc.returncode
    require(proc.returncode == 0, "native link failed; see private log")
    product = root / "bin" / DSO
    receipt["relinked"] = interface(product, root, "relinked")
    receipt["equal"] = {k: v == receipt["relinked"][k] for k, v in receipt["original"].items()}
    receipt["allocated_bytes_before_receipt"] = sum(
        f.stat().st_blocks * 512 for f in root.rglob("*") if f.is_file()
    )
    require(receipt["allocated_bytes_before_receipt"] < LIMIT - 65536, "output budget")
    receipt["decision"] = (
        "PASS_RELINK_BYTE_IDENTICAL"
        if all(receipt["equal"].values())
        else "NO_GO_RELINK_BYTE_IDENTITY"
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    for arg in ("build-root", "c317-protocol", "new-output-dir"):
        cli.add_argument("--" + arg, type=Path, required=True)
    cli.add_argument("--exploratory", action="store_true")
    a = cli.parse_args()
    root, build = a.new_output_dir.resolve(), a.build_root.resolve()
    require(not root.is_relative_to(build), "destination inside source build")
    os.umask(0o077)
    root.mkdir(exist_ok=False)
    start = time.monotonic()
    receipt = {
        "schema": "c305-native-control-relink-v1",
        "decision": "FAIL_PRESERVED",
        "link_invocations": 0,
    }
    try:
        test(build, a.c317_protocol, root, a.exploratory, receipt)
    except Exception as error:
        receipt["error"] = f"{type(error).__name__}: {error}".replace(
            str(root), "<private>"
        ).replace(str(build), "<build>")
    receipt["elapsed_s"] = time.monotonic() - start
    pending = root / ".receipt.pending"
    pending.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
    pending.rename(root / "receipt.json")
    print(receipt["decision"])
    return 1 if receipt["decision"] == "FAIL_PRESERVED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
