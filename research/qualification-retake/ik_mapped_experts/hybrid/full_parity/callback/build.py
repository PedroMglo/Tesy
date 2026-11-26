"""Link a callback-selectable C110 client after reproducing the sealed ON executable."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
ORIGINAL = run_path(str(HERE.parent / "build.py"))
T = ORIGINAL["T"]
need, sha, pin = T["need"], T["sha"], T["pin"]
ORIGINAL_BUILD = "7e576aad09724f9de6ecd01084a8c8d555aed2f9bc9ed462129480bd90332478"
ORIGINAL_ELF = "ae22e3b4ece6120ffc7b513a1d597968994e65c6ddcccbc4a1e872896d8b9374"
SELECTOR = "TESY_C110_CALLBACK"


def render(source):
    anchor = "    auto ids=read_input(argv[4]);"
    select = """    const char *selection = std::getenv("TESY_C110_CALLBACK");
    must(selection && (std::string_view(selection) == "ON" || std::string_view(selection) == "OFF"),
         "TESY_C110_CALLBACK must be ON or OFF");
    const bool use_callback = std::string_view(selection) == "ON";
    std::printf("CB_EVAL %s\\n", selection);
"""
    src = ORIGINAL["once"](source, anchor, select + anchor)
    return ORIGINAL["once"](
        src, "p.cb_eval=callback;", "p.cb_eval=use_callback ? callback : nullptr;"
    )


def probe_selector(exe, search):
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LD_LIBRARY_PATH": os.pathsep.join(search)}
    # The sealed ID reader rejects /dev/null before opening the model or initialising llama.
    cmd = [str(exe), "BANK288", "/dev/null", "/dev/null", "/dev/null", "/dev/null"]
    result = {}
    for value in (None, "invalid", "OFF", "ON"):
        each = dict(env)
        if value is not None:
            each[SELECTOR] = value
        p = subprocess.run(cmd, env=each, capture_output=True, text=True, timeout=10)
        markers = [r for r in p.stdout.splitlines() if r.startswith("CB_EVAL ")]
        valid = value in ("OFF", "ON")
        expected = "expected 17 supplied IDs" if valid else "TESY_C110_CALLBACK must be ON or OFF"
        need(p.returncode == 1 and expected in p.stderr, "selector or early stop")
        need(markers == ([f"CB_EVAL {value}"] if valid else []), "selector marker")
        result["unset" if value is None else value] = {"rc": p.returncode, "markers": markers}
    return result


def build(a, out):
    historical = json.loads(pin(a.original / "receipt.json", ORIGINAL_BUILD).read_bytes())
    pin(a.original / "parity-client", ORIGINAL_ELF)
    need(historical["binary_sha256"] == ORIGINAL_ELF, "original ELF receipt")
    control = out / "control"
    control.mkdir()
    a.capacity_sha256 = historical["capacity_client_sha256"]
    b = ORIGINAL["build"](a, control)
    for key in (
        "binary_sha256",
        "compiler_sha256",
        "sources",
        "libraries",
        "closure",
        "explicit_search",
        "native_search_sha256",
        "inputs_sha256",
        "dso_build_sha256",
    ):
        need(b[key] == historical[key], "recompiled control differs: " + key)
    original = (control / "parity.cpp").read_text()
    src = out / "parity.cpp"
    src.write_text(render(original))
    exe = out / "callback-client"
    replace = {str(control / "parity.cpp"): str(src), str(control / b["binary"]): str(exe)}
    cmd = b["compile_argv"]
    need(all(cmd.count(k) == 1 for k in replace), "compiler source or destination")
    cmd = [replace.get(v, v) for v in cmd]
    with (out / "compiler.log").open("xb") as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
    ds = json.loads(pin(a.dso_build / "receipt.json", b["dso_build_sha256"]).read_bytes())
    search, closure = T["device_closure"](exe, a.dso_build.resolve() / "objects", ds, a)
    need(closure == historical["closure"] and search == historical["explicit_search"], "loader")
    return dict(
        status="PASS_CALLBACK_CLIENT_BUILD",
        commit=b["commit"],
        tree=b["tree"],
        original_receipt_sha256=ORIGINAL_BUILD,
        control_elf_sha256=sha(control / b["binary"]),
        original_source_sha256=b["sources"]["parity.cpp"],
        source_sha256=sha(src),
        binary=exe.name,
        binary_sha256=sha(exe),
        compiler_sha256=b["compiler_sha256"],
        build_script_sha256=sha(Path(__file__)),
        protocol_sha256=sha(HERE / "protocol.md"),
        dso_sha256=b["dso_build_sha256"],
        inputs_sha256=b["inputs_sha256"],
        libraries=b["libraries"],
        explicit_search=search,
        closure=closure,
        compile_argv=cmd,
        no_model_selector=probe_selector(exe, search),
        model_loads=0,
        forwards=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in (
        "original",
        "source",
        "dso-build",
        "capacity-build",
        "env49-map",
        "ids",
        "new-output-dir",
    ):
        parser.add_argument("--" + key, type=Path, required=True)
    a = parser.parse_args()
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    try:
        result = build(a, out)
    except Exception as exc:
        result = {"status": "FAIL_PRESERVED", "reason": str(exc)}
    with (out / "receipt.json").open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")
    print(result["status"], result.get("reason", ""))
    raise SystemExit(result["status"] == "FAIL_PRESERVED")
