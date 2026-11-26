"""Rebuild the pinned common library and exercise its public server proposer without weights."""

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
CTX = run_path(str(HERE.parent / "context_filter.py"))
H, G, need, sha, save = (CTX[k] for k in ("H", "G", "need", "sha", "save"))
PLAN = H["F"]
METHOD = "4f889f03ea2c6fe9939dbc1bc9359595b2fc9eb9e9df1180eb9dc61e970906b2"
CONFIG = {
    "compile_commands.json": "2582285bc2b5b7af91570e5c9f4ca326c34bdc6da2ec7aef53ce87c393f6fb6c",
    "build.ninja": "34c0ff3554a9637e3829131a641ff799fc04b94051d9c71999a95eacb6381d21",
    "CMakeFiles/rules.ninja": "049f8d12e3b9f38440a4169cbf76753d3acd78cdd2dab53ac4bfe7ed731842ff",
}
SOURCE = "4bedd358b43833f6f10bd11c254da7b5bcae779fc58a4f577032cc0b3a9a4732"
OLD_OBJECT = "344ed0cbf739d89b4d4cb79d40ee3635731419111a552b3c4e7ae9688c95d471"
GCC = "cef5002fbce633104c81b24e9fd935251ab653234c8dce8758d3c963d6123c8a"
SWITCH = "TESY_NGRAM_PREVIOUS_TOKEN"


def recipes(backend):
    build = backend / "build-c269-cuda"
    need(
        all(sha(build / k) == v for k, v in CONFIG.items()) and sha(Path("/usr/bin/g++-15")) == GCC,
        "build configuration",
    )
    (entry,) = [
        x
        for x in json.loads((build / "compile_commands.json").read_bytes())
        if x["file"].endswith("/common/ngram-map.cpp")
    ]
    compile = shlex.split(entry["command"])
    src = Path(entry["file"])
    need(src.resolve() == backend / "common/ngram-map.cpp" and sha(src) == SOURCE, "source pin")
    obj = compile[compile.index("-o") + 1]
    need(sha(build / obj) == OLD_OBJECT, "installed original object")
    entries = subprocess.check_output(
        ["/usr/bin/ninja", "-C", build, "-t", "commands", "bin/libllama-common.so.0.0.9884"],
        text=True,
    )
    wrapped = shlex.split(entries.splitlines()[-1])
    need(
        wrapped[:3] == [":", "&&", "/usr/bin/g++-15"]
        and wrapped[-2:] == ["&&", ":"]
        and obj in wrapped,
        "link command",
    )
    link = wrapped[2:-2]
    inputs = {
        v: sha(build / v)
        for v in link[1:]
        if not v.startswith("-") and (build / v).is_file() and v != link[link.index("-o") + 1]
    }
    need(
        inputs[obj] == OLD_OBJECT and "common/libllama-common-base.a" in inputs,
        "original link providers",
    )
    return build, src, obj, compile, link, inputs


def library(name, out, recipe, env):
    build, src, obj, cc, link, _ = recipe
    arm = out / name
    (arm / "common").mkdir(parents=True)
    cpp = arm / "common/ngram-map.cpp"
    shutil.copyfile(src, cpp)
    if name == "FILTER":
        G["command"](
            ["/usr/bin/patch", "--batch", "--fuzz=0", "-p1", "-i", HERE / "previous-token.patch"],
            arm,
            arm,
            "patch",
            env,
        )
    newobj = arm / "ngram-map.cpp.o"
    before = list(cc)
    before[before.index("-c") + 1] = str(cpp)
    before[before.index("-o") + 1] = str(newobj)
    before[1:1] = [
        "-fmacro-prefix-map=" + str(cpp) + "=" + str(src),
        "-MD",
        "-MF",
        str(arm / "headers.d"),
    ]
    G["command"](before, build, arm, "compile", env)
    headers = G["headers"](arm / "headers.d", build)
    need(headers.pop(str(cpp)) == sha(cpp), "actual source dependency")
    save(arm / "headers.json", headers)
    so = arm / "libllama-common.so.0"
    after = list(link)
    after[after.index("-o") + 1] = str(so)
    after[after.index(obj)] = str(newobj)
    deps = [i for i, v in enumerate(after) if v.startswith("-Wl,--dependency-file=")]
    need(len(deps) == 1, "one private linker dependency file")
    after[deps[0]] = "-Wl,--dependency-file=" + str(arm / "link.d")
    G["command"](after, build, arm, "link", env)
    if name == "CONTROL":
        need(
            sha(newobj) == OLD_OBJECT and sha(so) == PLAN["OLD"]["COMMON"],
            "byte-identical original object and common DSO",
        )
    else:
        need(sha(so) != PLAN["OLD"]["COMMON"] and SWITCH in cpp.read_text(), "new library")
    return so, dict(
        ELF_sha256=sha(so),
        object_sha256=sha(newobj),
        source_sha256=sha(cpp),
        headers_sha256=G["digest"](headers),
    )


def compare(rows, case, function):
    target = case["target"]
    past = tuple(case["prompt"]) + (target[0],)
    at = 1
    depths = Counter()
    sites = []
    for row in rows:
        room = max(0, min(8192 - len(past) - 1, case["cap"] - at - 1))
        expected = function(past, room)
        need(
            row["at"] == at and tuple(row["proposal"]) == expected and row["room"] == room,
            "native proposal/remaining room",
        )
        accepted = 0
        while (
            accepted < len(expected)
            and at + accepted < len(target)
            and target[at + accepted] == expected[accepted]
        ):
            accepted += 1
        emitted = min(len(target) - at, accepted + 1)
        need(
            row["accepted"] == accepted
            and row["emitted"] == emitted
            and row["unobserved_bonus"] == (at + accepted == len(target)),
            "target response",
        )
        if expected:
            sites.append(at)
            depths[accepted] += 1
        past += tuple(target[at : at + emitted])
        at += emitted
    need(past == tuple(case["prompt"]) + tuple(target) and at == len(target), "complete target IDs")
    return dict(
        serial=len(rows) - len(sites),
        positions=sites,
        depths=[depths[k] for k in (0, 1, 2)],
        target_count=at,
    )


def native(out, exe, options, env, data, label):
    root = out / label
    root.mkdir()
    raw = json.dumps(data, allow_nan=False).encode()
    p = subprocess.run([exe, *options], input=raw, env=env, timeout=30, capture_output=True)
    (root / "proposals.json").write_bytes(p.stdout)
    (root / "stderr").write_bytes(p.stderr)
    need(p.returncode == 0, "dispatcher " + label)
    return json.loads(p.stdout), hashlib.sha256(p.stdout).hexdigest()


def run(a, out, r):
    head, tree = G["tree"](G["REPO"])
    group = Path("/sys/fs/cgroup") / Path(
        Path("/proc/self/cgroup").read_text().strip()[3:]
    ).relative_to("/")
    need(
        head == a.commit
        and sha(HERE / "protocol.md") == METHOD
        and (group / "memory.max").read_text().strip() == str(2 << 30)
        and (group / "memory.swap.max").read_text().strip() == "0",
        "frozen study and resource caps",
    )
    need(G["tree"](a.backend)[0] == PLAN["OLD"]["C269"], "C269 pin")
    plan = G["read"](a.plan / "receipt.json", H["PLAN_PIN"])
    static = G["read"](a.static / "receipt.json", G["STATIC"])["arms"]["C281_PACK"]
    need(
        plan["common_sha256"] == PLAN["OLD"]["COMMON"]
        and sha(Path(static["binary"])) == plan["server_sha256"],
        "server and dispatcher identities",
    )
    env = dict(
        PATH="/usr/bin:/bin",
        LC_ALL="C",
        LANG="C",
        TMPDIR=str(out),
        CUDA_VISIBLE_DEVICES="",
        LD_LIBRARY_PATH=os.pathsep.join(static["search"]),
    )
    recipe = recipes(a.backend)
    save(out / "link-inputs.json", recipe[-1])
    images = {}
    files = {}
    for mode in ("CONTROL", "FILTER"):
        images[mode], files[mode] = library(mode, out, recipe, env)
    r.update(
        commit=head,
        tree=tree,
        images=files,
        installed_server_sha256=plan["server_sha256"],
        link_inputs_sha256=sha(out / "link-inputs.json"),
    )
    args = G["read"](a.plan / "compile-argv.json", plan["files"]["compile-argv.json"])
    need(
        args[0] == "/usr/bin/g++-15"
        and args[-2] == "-o"
        and len([k for k in args if k.endswith("/server_plan.cpp")]) == 1,
        "prior CLI fixture recipe",
    )
    exe = out / "server-plan"
    args[args.index("-MF") + 1] = str(out / "driver.d")
    args[-1] = str(exe)
    src = Path(PLAN["__file__"]).parent / "server_plan.cpp"
    args[next(i for i, k in enumerate(args) if k.endswith("/server_plan.cpp"))] = str(src)
    G["command"](args, out, out, "driver", env)
    observed = G["headers"](out / "driver.d", out)
    need(
        observed.pop(str(src)) == sha(src)
        and {str(Path(k).relative_to(a.backend)): v for k, v in observed.items()}
        == plan["headers"],
        "pinned driver headers",
    )
    data = PLAN["inputs"](a)
    opt = list(plan["options"])
    good = (9, 6, 2, 3, 7, 8, 0, 6, 2, 3)
    wrong = good[:-3] + (5, 2, 3)
    recent = (9, 6, 2, 3, 1, 2, 0, 4, 2, 3, 7, 8, 0, 6, 2, 3)
    demos = {"agree": good, "disagree": wrong, "recent": recent, "short": good[:5]}
    fixtures = {
        k: dict(prompt=list(v[:-1]), target=[v[-1], 7, 8, 9], cap=10) for k, v in demos.items()
    }
    all_cases = data | fixtures
    output = {}
    libraries = {}
    digests = {}
    for name, image, n, enabled in (
        ("N2", "CONTROL", 2, False),
        ("N3", "CONTROL", 3, False),
        ("OFF", "FILTER", 2, False),
        ("ON", "FILTER", 2, True),
    ):
        e = env | dict(
            LD_LIBRARY_PATH=str(images[image].parent) + os.pathsep + env["LD_LIBRARY_PATH"]
        )
        if enabled:
            e[SWITCH] = "1"
        deps = G["START"]["interpret"](
            subprocess.check_output(["/usr/bin/ldd", "-r", exe], env=e, text=True)
        )
        closure = {k: sha(v.resolve(strict=True)) for k, v in deps.items()}
        need(
            closure == plan["providers"] | {"libllama-common.so.0": sha(images[image])}
            and deps["libllama-common.so.0"].resolve() == images[image],
            "actual proposer bindings",
        )
        libraries[name] = G["digest"](closure)
        opts = opt.copy()
        opts[opts.index("--spec-ngram-simple-size-n") + 1] = str(n)
        if name == "N2":
            _, gold = native(out, exe, opts, e, data, "historic")
            need(gold == plan["same_output_sha256"], "all original rows bit for bit")
        raw, digests[name] = native(out, exe, opts, e, all_cases, name)
        fn = (
            (lambda history, room: PLAN["RULE"]["draft"](history, 3, 2)[:room])
            if n == 3
            else (lambda history, room, active=enabled: CTX["proposal"](history, room, active))
        )
        need(raw.keys() == all_cases.keys(), "fixture coverage")
        output[name] = {k: compare(raw[k], v, fn) for k, v in all_cases.items()}
    need(
        digests["N2"] == digests["OFF"]
        and all(not row["positions"] for row in output["N3"].values()),
        "OFF or stock trigram",
    )
    need(
        output["ON"]["agree"]["positions"][0] == 1
        and 1 not in output["ON"]["recent"]["positions"]
        and 1 in output["OFF"]["recent"]["positions"]
        and [output["ON"][k]["depths"] for k in ("T1", "T2")] == [[3, 0, 4], [1, 3, 3]],
        "strict filter",
    )
    r.update(
        status="GO_NATIVE_CONTEXT_FILTER_ONLY",
        dispatcher_sha256=sha(exe),
        arms=output,
        raw_digests=digests,
        closures=libraries,
        historical_rows_sha256=gold,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("backend", "plan", "static", "capture", "verified", "new-output-dir"):
        p.add_argument("--" + k, required=True, type=Path)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    r = dict(status="FAIL_PRESERVED", protocol_sha256=METHOD, model_starts=0, http_requests=0)
    start = time.monotonic()
    try:
        run(a, out, r)
    except Exception as exc:
        r["error"] = f"{type(exc).__name__}: {exc}"
    r["wall_s"] = time.monotonic() - start
    save(out / "result.json", r)
    print(r["status"], r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
