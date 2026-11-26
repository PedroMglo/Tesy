"""Run C281's CLI and speculative dispatcher twice on the sealed natural T1 and T2 IDs."""

import argparse
import hashlib
import json
import os
import shlex
import signal
import struct
import subprocess
import time
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[4]
GRAPH = run_path(str(HERE.parents[1] / "build.py"))
OLD = run_path(str(QUAL / "history_lookup/native_ids/b3_fixture/run.py"))
RULE = run_path(str(QUAL / "history_lookup/causal_pair/screen.py"))
need, sha, save = GRAPH["need"], GRAPH["sha"], GRAPH["save"]
METHOD = "649b6f07257fab7f0125dabd33caaa1321d8154c08f342829ab0195c67960540"
GATE = "6c3c96649a8226d97874569bb8012c925bc7781a85fa5bd65875709d1cc99e5e"


def inputs(a):
    verified = GRAPH["read"](a.verified / "receipt.json", OLD["VERIFIED"])
    GRAPH["read"](a.capture / "receipt.json", OLD["CAPTURE"])
    data = {}
    for i, name in enumerate(("T1", "T2")):
        ref = verified["turns"][i]
        label = name + "-input.json"
        row = GRAPH["read"](a.capture / "raw" / label, verified["capture_turn_files_sha256"][label])
        tokens = row["official_ids"]
        observed = a.verified / (name + "-sampled.i32")
        need(
            ref["unique_final_eog"]
            and ref["label"] == name
            and sha(observed) == ref["sampled_ids_sha256"]
            and len(tokens) == (2043, 2197)[i]
            and ref["count"] == (78, 47)[i]
            and hashlib.sha256(struct.pack(f"<{len(tokens)}i", *tokens)).hexdigest()
            == ref["official_ids_sha256"],
            "real prompt and target bytes",
        )
        sampled = list(struct.unpack(f"<{ref['count']}i", observed.read_bytes()))
        data[name] = dict(prompt=tokens, target=sampled, cap=256)
    # The first step has precisely one draft slot left under cap=3.
    data["cap"] = dict(prompt=[9, 1, 2, 3, 4, 8, 9, 1], target=[2, 3, 4], cap=3)
    return data


def validate(rows, entry):
    target = entry["target"]
    history = tuple(entry["prompt"]) + (target[0],)
    seen = 1
    widths, depths = Counter(), Counter()
    unresolved = 0
    for row in rows:
        room = min(8192 - len(history) + 1 - 2, entry["cap"] - seen - 1)
        expected = RULE["draft"](history, 2, 2)[: max(0, room)]
        need(
            row["at"] == seen and row["room"] == room and tuple(row["proposal"]) == expected,
            "causal proposal",
        )
        k = 0
        while k < len(expected) and seen + k < len(target) and expected[k] == target[seen + k]:
            k += 1
        count = min(len(target) - seen, 1 + k)
        need(
            row["accepted"] == k
            and row["emitted"] == count
            and row["unobserved_bonus"] == (seen + k == len(target)),
            "target consumption",
        )
        history += tuple(target[seen : seen + count])
        seen += count
        widths[len(expected) + 1] += 1
        if expected:
            depths[k] += 1
        unresolved += int(row["unobserved_bonus"])
    need(
        seen == len(target) and history == tuple(entry["prompt"]) + tuple(target),
        "terminal target history",
    )
    blocks = sum(depths.values())
    headroom = (len(target) - 1 - widths[1]) / blocks if blocks and not widths[2] else None
    return dict(
        prompt_ids=len(entry["prompt"]),
        sampled_ids=seen,
        call_widths={str(k): widths[k] for k in (1, 2, 3)},
        accepted_per_proposal={str(k): depths[k] for k in (0, 1, 2)},
        unobserved_bonus=unresolved,
        mean_B3_to_uniform_AR_at_decode_break_even=headroom,
    )


def run(a, out, r):
    commit, tree = GRAPH["tree"](GRAPH["REPO"])
    need(
        commit == a.commit
        and sha(HERE / "protocol.md") == METHOD
        and sha(Path(RULE["__file__"])) == OLD["RULE_SHA"],
        "study source",
    )
    physical = GRAPH["read"](a.physical / "receipt.json", GATE)
    need(
        physical["status"] == "GO_PACKED_SERVER_RESERVE_GREEDY" and physical["model_starts"] == 7,
        "packed gate",
    )
    data = inputs(a)
    cg = Path("/sys/fs/cgroup") / Path(
        Path("/proc/self/cgroup").read_text().strip()[3:]
    ).relative_to("/")
    need(
        cg.name.startswith("tesy-packed-causal-plan-")
        and (cg / "memory.max").read_text().strip() == str(1 << 30)
        and (cg / "memory.swap.max").read_text().strip() == "0",
        "bounded model-free process",
    )
    static = GRAPH["read"](a.static / "receipt.json", GRAPH["STATIC"])["arms"]["C281_PACK"]
    need(
        sha(Path(static["binary"])) == static["binary_sha256"]
        and GRAPH["tree"](a.backend)[0] == OLD["C269"],
        "C281 and C269",
    )
    dso = Path(static["closure"]["libllama-common.so.0"]["file"])
    need(sha(dso) == OLD["COMMON"], "shared proposer and dispatcher")
    driver = Path("/usr/bin/g++-15")
    need(
        sha(driver) == "cef5002fbce633104c81b24e9fd935251ab653234c8dce8758d3c963d6123c8a",
        "compiler",
    )
    exe = out / "server-plan"
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "LANG": "C",
        "TMPDIR": str(out),
        "CUDA_VISIBLE_DEVICES": "",
        "LD_LIBRARY_PATH": os.pathsep.join(static["search"]),
    }
    cmd = [driver, "-O0", "-g0", "-std=c++17", "-MMD", "-MF", out / "headers.d"]
    for folder in ("common", "include", "ggml/include", "vendor", "vendor/nlohmann"):
        cmd += ["-I", a.backend / folder]
    cmd += [HERE / "server_plan.cpp", dso, "-Wl,-rpath-link," + str(dso.parent), "-o", exe]
    GRAPH["command"](cmd, out, out, "compile", env)
    deps = shlex.split(
        (out / "headers.d").read_text().replace(chr(92) + "\n", " ").split(":", 1)[1]
    )
    headers = {}
    for dep in map(Path, deps):
        dep = dep.resolve(strict=True)
        if dep == HERE / "server_plan.cpp":
            continue
        relative = dep.relative_to(a.backend)
        blob = subprocess.check_output(
            ["git", "-C", a.backend, "show", OLD["C269"] + ":" + str(relative)]
        )
        need(blob == dep.read_bytes(), "unbound header")
        headers[str(relative)] = hashlib.sha256(blob).hexdigest()
    need("common/speculative.h" in headers and "common/arg.h" in headers, "public API")
    projections = {}
    logfile = subprocess.check_output(["/usr/bin/ldd", "-r", exe], env=env, text=True, timeout=30)
    (out / "runtime.ldd").write_text(logfile)
    for key, file in GRAPH["START"]["interpret"](logfile).items():
        dest = file.resolve(strict=True)
        need(
            str(dest) == static["closure"][key]["file"]
            and sha(dest) == static["closure"][key]["sha256"],
            "C281 provider " + key,
        )
        projections[key] = sha(dest)
    options = [
        "--offline",
        "--spec-type",
        "ngram-simple",
        "--spec-ngram-simple-size-n",
        "2",
        "--spec-ngram-simple-size-m",
        "2",
        "--spec-ngram-simple-min-hits",
        "1",
        "-np",
        "1",
        "-c",
        "8192",
        "-b",
        "256",
        "-ub",
        "32",
    ]
    r.update(
        commit=commit,
        tree=tree,
        physical_sha256=GATE,
        protocol_sha256=METHOD,
        common_sha256=sha(dso),
        binary_sha256=sha(exe),
        server_sha256=static["binary_sha256"],
        headers=headers,
        providers=projections,
        options=options,
    )
    payload = json.dumps(data, allow_nan=False).encode()
    results = []
    for i in range(2):
        p = subprocess.run([exe, *options], input=payload, env=env, timeout=30, capture_output=True)
        (out / f"r{i}.stdout").write_bytes(p.stdout)
        (out / f"r{i}.stderr").write_bytes(p.stderr)
        need(p.returncode == 0, "native replay " + str(i))
        record = json.loads(p.stdout)
        need(record.keys() == data.keys(), "three cases")
        results.append({k: validate(record[k], v) for k, v in data.items()})
    need(
        (out / "r0.stdout").read_bytes() == (out / "r1.stdout").read_bytes()
        and results[0] == results[1],
        "independent reproduction",
    )
    need(results[0]["cap"]["call_widths"]["2"] == 1, "cap truncates one real proposal")
    need(
        results[0]["T2"]["call_widths"] == {"1": 23, "2": 0, "3": 11}
        and results[0]["T2"]["accepted_per_proposal"] == {"0": 5, "1": 0, "2": 6},
        "independent C281 T2",
    )
    r.update(
        status="GO_CAUSAL_SERVER_PLAN", turns=results[0], same_output_sha256=sha(out / "r0.stdout")
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("physical", "capture", "verified", "static", "backend", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    r = dict(status="FAIL_PRESERVED", model_starts=0, generation_requests=0)

    def expire(*_):
        raise TimeoutError("three minute cap")

    signal.signal(signal.SIGALRM, expire)
    signal.alarm(180)
    t0 = time.monotonic()
    try:
        run(a, out, r)
    except Exception as e:
        r["status"] = "FAIL_PRESERVED"
        r["error"] = f"{type(e).__name__}: {e}"
    finally:
        signal.alarm(0)
    r["wall_s"] = time.monotonic() - t0
    r["files"] = {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()}
    save(out / "receipt.json", r)
    print(r["status"], r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
