"""Authenticate a closed C269 DEBUG session and match its two chat streams offline."""

import argparse
import hashlib
import json
import os
import re
import shlex
import struct
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]
HISTORICAL = "cb191e31c2e3ee547a01228065a3c4253bdb312dd1e561d361f75365f065356a"
EVIDENCE = "42614a3e1c6f4fc137b87f06c002faa0be74ff3f8d32c69840292d75b9585be4"
VOCAB = "ac4566b560fe2df4e0f4f9eb071ce8803af7107c022b4a643a842560ba8b7049"
BUILD = "e9662585b863443bb74d088701f5fc580d03ae7be344cc9f899df523246afe58"
WITNESS = "4b801978eef46ebec37482698a4a3343b5646ec34c0081ba27c7c833ae6e8d29"
C269 = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
GEOMETRY = ((2043, 0, 78, 71), (2197, 2044, 47, 40))
CAP = 64 * 1024 * 1024
SOURCE = {
    "tools/server/server-context.cpp": (
        "657c331a707f0faf74615d19387088070c3dbd7559328619c9ef606a4ec8cc55"
    ),
    "common/log.cpp": "be54107a3334c3e74439b4a3a694822e61cf918725fa401d9921a53e27d9a7fb",
}
# Prefix/timestamps are already on in C281. Only verbosity changes.
CLOCK = rb"(?m)^([0-9]+)\.([0-5][0-9])\.([0-9]{3})\.([0-9]{3}) "
HEADER = re.compile(
    CLOCK + rb"([ID]) slot (launch_slot_|handle_last_|process_toke|     release): "
    rb"id ([ 0-9]{2}) \| task ([0-9]+) \| "
)
SAMPLE = re.compile(rb"n_decoded = ([0-9]+), n_remaining = (-?[0-9]+), next token: ( *[0-9]+) '")
FEED = re.compile(
    rb"slot decode token, id=([0-9]+), n_ctx = 8192, n_tokens = ([0-9]+), truncated = 0\n"
)
RELEASE = re.compile(rb"stop processing: n_tokens = ([0-9]+), truncated = 0\n")


class Gate(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise Gate(message)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pinned(path, expected):
    need(sha(path) == expected, "file hash")


def read(path):
    need(path.is_file() and path.stat().st_size <= CAP, "file type or size")
    return json.loads(path.read_bytes())


def ids_bytes(ids):
    need(all(type(t) is int and 0 <= t < 201088 for t in ids), "token range")
    return struct.pack(f"<{len(ids)}i", *ids)


def events(log):
    for row in HEADER.finditer(log):
        clock = tuple(int(x) for x in row.groups()[:4])
        level, function, slot, task = row.groups()[4:]
        p = row.end()
        if function == b"launch_slot_" and log.startswith(b"processing task, is_child = 0\n", p):
            event = ("start",)
        elif function == b"handle_last_" and log.startswith(b"slot decode token,", p):
            arg = FEED.match(log, p)
            need(arg, "malformed batch witness")
            event = ("feed", int(arg[1]), int(arg[2]))
        elif function == b"process_toke" and log.startswith(b"n_decoded", p):
            arg = SAMPLE.match(log, p)
            need(arg, "malformed sampler witness")
            n, left, raw_id = arg.groups()
            token = int(raw_id)
            need(token < 201088 and raw_id == b"%5d" % token, "noncanonical token ID")
            event = ("sample", int(n), int(left), token, arg.end())
        elif function == b"process_toke" and log.startswith(b"stopped by EOS\n", p):
            event = ("eos",)
        elif function == b"     release" and log.startswith(b"stop processing:", p):
            arg = RELEASE.match(log, p)
            need(arg, "malformed release")
            event = ("end", int(arg[1]))
        else:
            continue
        need(
            slot == b" 0" and level == (b"I" if event[0] in {"start", "end"} else b"D"),
            "slot or log level",
        )
        yield clock, int(task), event


def trajectories(log, geometry=GEOMETRY):
    """A forged record in quoted data adds an event and fails the closed lifecycle."""
    stream = iter(events(log))
    last_clock = (-1,)
    seen = set()

    def take(kind, task=None):
        nonlocal last_clock
        entry = next(stream, None)
        need(entry is not None, "missing native event")
        clock, owner, event = entry
        need(clock >= last_clock and event[0] == kind, "native event order")
        need(task is None or owner == task, "native task association")
        last_clock = clock
        return owner, event

    turns = []
    for prompt, _, count, _ in geometry:
        task, _ = take("start")
        need(task not in seen, "task reused")
        seen.add(task)
        samples = []
        for n in range(1, count + 1):
            if n == count:
                take("eos", task)
            _, (_, number, remaining, token, offset) = take("sample", task)
            need(number == n and remaining == 256 - n, "sampling count or budget")
            samples.append((token, offset))
            if n < count:
                _, (_, fed, position) = take("feed", task)
                need(fed == token and position == prompt + n - 1, "batch token or position")
        _, (_, position) = take("end", task)
        need(position == prompt + count - 1, "release position")
        turns.append(samples)
    need(next(stream, None) is None, "extra native event")
    return turns


def piece_rows(log, samples, pieces):
    need(len(pieces) == len(samples), "piece count")
    for (_, offset), piece in zip(samples, pieces, strict=True):
        # C269 logs the original token_str through printf %s. UTF-8 and LF
        # are raw bytes and a NUL truncates only this textual field.
        need(
            log.startswith(piece.partition(b"\0")[0] + b"'\n", offset), "native piece or delimiter"
        )


def projection(raw, i, geometry):
    label = f"T{i}"
    inp = read(raw / (label + "-input.json"))
    result = read(raw / (label + "-result.json"))
    prompt, cache, count, frames_n = geometry
    usage = {
        "prompt_tokens": prompt,
        "completion_tokens": count,
        "total_tokens": prompt + count,
        "prompt_tokens_details": {"cached_tokens": cache},
    }
    ids = inp["official_ids"]
    need(ids == result["official_ids"] and len(ids) == prompt, "full official prompt")
    need(result["common_prefix"] == (None if i == 1 else 2043), "inter-turn official prefix")
    need(
        result["usage"] == usage
        and result["finish_reason"] == "stop"
        and result["accepted"] is True
        and result["content_gate"] == result["prefix_gate"] == "PASS",
        "product validation",
    )
    need(
        result["timings"]["cache_n"] == cache
        and result["timings"]["prompt_n"] == prompt - cache
        and result["timings"]["predicted_n"] == count
        and result["output_ids"] is None,
        "token denominators",
    )
    journal = raw / (label + "-request.jsonl")
    need(journal.stat().st_size <= CAP, "journal size")
    rows = [json.loads(line) for line in journal.read_bytes().splitlines()]
    need(
        rows[0]["kind"] == "REQUEST_START"
        and rows[-1]["kind"] == "REQUEST_TERMINAL"
        and rows[-1]["accepted"] is True,
        "transport terminal",
    )
    fragments = [
        r["fragment"].strip()
        for r in rows
        if r["kind"] == "SSE_FRAGMENT" and r["fragment"].strip() not in ("", ":")
    ]
    need(
        fragments
        and fragments[-1] == "data: [DONE]"
        and all(s.startswith("data: {") for s in fragments[:-1]),
        "SSE framing",
    )
    frames = [json.loads(s[6:]) for s in fragments[:-1]]
    need(len(frames) == frames_n and frames[-1]["usage"] == usage, "chat frame geometry")
    verbose = [r["__verbose"] for r in frames if "__verbose" in r]
    need(len(verbose) == 1, "server metadata cardinality")
    v = verbose[0]
    g = v["generation_settings"]
    need(
        v["stop_type"] == "eos"
        and v["stop"] is True
        and not v["truncated"]
        and not v["stopping_word"]
        and v["id_slot"] == 0
        and v["tokens"] == []
        and v["tokens_predicted"] == count
        and v["tokens_evaluated"] == prompt
        and v["tokens_cached"] == prompt + count - 1,
        "native EOS or totals",
    )
    need(
        g["chat_format"] == "peg-native"
        and g["generation_prompt"] == "<|start|>assistant"
        and g["reasoning_format"] == "deepseek"
        and not g["reasoning_in_content"]
        and g["speculative.types"] == "none"
        and not g["stop"]
        and not g["grammar"]
        and not g["ignore_eos"]
        and not g["n_probs"]
        and not g["logit_bias"]
        and g["n_predict"] == 256
        and g["temperature"] == 0
        and g["seed"] == 42
        and len(g["preserved_tokens"]) == 5,
        "generation settings",
    )
    projected = [{k: f[k] for k in ("choices", "usage") if k in f} for f in frames]
    return inp, result["message"], projected, g


def historic_manifest(root):
    path = BASE / "nvme_conversation/postupdate/physical-r01/evidence.json"
    pinned(path, EVIDENCE)
    reference = read(path)
    pinned(root / "receipt.json", HISTORICAL)
    files = {}
    for p in root.rglob("*"):
        need(not p.is_symlink(), "historical symlink")
        if p.is_file():
            files[p.relative_to(root).as_posix()] = {"sha256": sha(p), "bytes": p.stat().st_size}
    seal = digest(json.dumps(files, sort_keys=True, separators=(",", ":")).encode())
    need(
        len(files) == reference["local_files"] and seal == reference["files_sha256"],
        "historical raw manifest",
    )
    return seal


def capture_log(root, historical, expected):
    pinned(root / "receipt.json", expected)
    rec = read(root / "receipt.json")
    native = rec["native_ids"]
    preset = root / "preset.json"
    pinned(preset, rec["preset_sha256"])
    rid = read(preset)["run_id"]
    need(isinstance(rid, str) and Path(rid).name == rid, "unit name")
    raw = root / "raw"
    monitor = raw / (rid + ".json")
    pinned(monitor, rec["monitor_sha256"])
    mon = read(monitor)
    authority = rec["runtime_authority"]
    need(
        rec["status"] == "PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY"
        and rec["model_launches"] == 1
        and rec["cleanup"] == "SERVER_EXIT_0_OWNER_STOP_UNIT_CLOSED_PORT_AVAILABLE"
        and mon["returncode"] == 0
        and mon["stop_reason"] == "INTERRUPTED_BY_OWNER"
        and authority["status"] == "PASS_LIVE_AND_LOADER_C281"
        and authority["native_pid"] == native["pid"],
        "capture lifecycle",
    )
    original = read(historical / "preset.json")["server_command"]
    command = [*original, "--log-verbosity", "5"]
    cmd_hash = digest(b"\0".join(map(os.fsencode, command)) + b"\0")
    need(
        native["verbosity"] == 5
        and native["port"] == 18442
        and native["argv_sha256"]
        == native["first_argv_sha256"]
        == native["last_argv_sha256"]
        == cmd_hash
        and native["native_task_source_sha256"] == SOURCE["tools/server/server-context.cpp"]
        and mon["command"] == command
        and mon["binary_sha256"]
        == native["server_sha256"]
        == "054e983528d35731e2dc6222f1418f2f08120ef83e0c5f2a8db11805dd38effa"
        and native["server_impl_sha256"]
        == "6e4786b127d8a0f2addd657b9842dade1c3f2b9262d088b84fb526ca04ed9206",
        "native identity",
    )
    for key, filename in (
        ("first_client", "first-client-map.json"),
        ("last_client", "last-client-map.json"),
    ):
        path = root / filename
        pinned(path, authority[key])
        stamp = read(path)
        need(
            stamp["pid"] == native["pid"]
            and stamp["mapped_sha256"]["libllama-server-impl.so"] == native["server_impl_sha256"],
            "native maps",
        )
    name = native["raw_stderr_file"]
    need(name == rid + ".stderr", "stderr basename")
    path = raw / name
    need(
        not path.is_symlink()
        and path.stat().st_size == native["stderr_bytes"] <= CAP
        and mon["output_sha256"][".stderr"] == native["stderr_sha256"],
        "stderr identity",
    )
    pinned(path, native["stderr_sha256"])
    return path.read_bytes(), rec, native


def native_projection(backends, vocab, turns, out):
    backend = backends / "c269-layer-last-use"
    lab = backends.parent
    server = (
        lab
        / "results/c276-post-c274-r2-causal-qualification-20261005T204839Z"
        / "build/persistent-server/bin"
    )
    libs = backend / "build-c269-cuda/bin"
    pinned(vocab, VOCAB)
    cert_path = HERE.parent / "natural47/evidence/build-r02.json"
    pinned(cert_path, BUILD)
    cert = read(cert_path)
    pinned(HERE.parent / "natural47/witness.cpp", WITNESS)
    need(
        subprocess.check_output(["git", "-C", backend, "rev-parse", "HEAD"], text=True).strip()
        == C269,
        "source revision",
    )
    for name, expected in (cert["headers_sha256"] | SOURCE).items():
        pinned(backend / name, expected)
    library_hashes = {
        name: value
        for name, value in cert["resolved_elf_sha256"].items()
        if name.startswith(("libggml", "libllama", "libmtmd"))
    }
    for name, expected in library_hashes.items():
        paths = [p for p in (server / name, libs / name) if p.exists()]
        need(paths and all(sha(p) == expected for p in paths), "native library")
    compiler = Path("/usr/bin/g++")
    pinned(compiler, cert["compiler_sha256"])
    exe, dep = out / "project", out / "headers.d"
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "CUDA_VISIBLE_DEVICES": "",
        "LD_LIBRARY_PATH": f"{server}:{libs}",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
    }
    source = HERE / "project.cpp"
    command = [
        compiler,
        "-std=c++17",
        "-O0",
        "-g0",
        "--param",
        "ggc-min-expand=8",
        "--param",
        "ggc-min-heapsize=8192",
        "-MMD",
        "-MF",
        dep,
    ]
    for include in (
        "include",
        "ggml/include",
        "common",
        "vendor",
        "vendor/nlohmann",
        "tools/server",
        "tools/mtmd",
        "src",
        "vendor/cpp-httplib",
    ):
        command.extend(["-I", backend / include])
    command.extend(
        [
            source,
            f"-L{server}",
            f"-L{libs}",
            f"-Wl,-rpath-link,{libs}",
            f"-Wl,-rpath-link,{server}",
            server / "libllama-server-impl.so",
            libs / "libllama-common.so",
            libs / "libllama.so",
            libs / "libggml-base.so",
            "-pthread",
            "-o",
            exe,
        ]
    )
    with (out / "compile.log").open("xb") as log:
        run = subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT, timeout=90, env=env, check=False
        )
    need(run.returncode == 0, "projection build")
    used = {
        Path(p).resolve()
        for p in shlex.split(dep.read_text().replace("\\\n", " ").split(":", 1)[1])
    }
    expected = {(backend / p).resolve() for p in cert["headers_sha256"]}
    need(
        used == expected | {source, (HERE.parent / "natural47/witness.cpp").resolve()},
        "projection headers",
    )
    paths = subprocess.check_output(["/usr/bin/ldd", exe], env=env, text=True)
    linked = {Path(x.split()[2]).resolve() for x in paths.splitlines() if " => /" in x}
    relevant = {
        p.name: sha(p) for p in linked if p.name.startswith(("libggml", "libllama", "libmtmd"))
    }
    need(relevant == library_hashes, "projection providers")
    run = subprocess.run(
        [exe, vocab],
        input=json.dumps(turns).encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=60,
        env=env,
        check=False,
    )
    need(run.returncode == 0, "C269 EOG, vocabulary or chat projection")
    return json.loads(run.stdout), {
        "executable_sha256": sha(exe),
        "provider_sha256": relevant,
        "source_sha256": sha(source),
        "headers_and_reference_sha256": BUILD,
    }


def run(a):
    historical = historic_manifest(a.historical)
    log, rec, native = capture_log(a.capture, a.historical, a.capture_sha256)
    samples = trajectories(log)
    requests, public, binaries = [], [], []
    for i, geometry in enumerate(GEOMETRY, 1):
        old = projection(a.historical / "raw", i, geometry)
        observed = projection(a.capture / "raw", i, geometry)
        need(
            old == observed,
            "historical versus observed input, complete message, choices or settings",
        )
        inp, _, frames, settings = observed
        prompt, cache, n, _ = geometry
        ids = [t for t, _ in samples[i - 1]]
        label = f"T{i}"
        packed = ids_bytes(ids)
        prompt_hash = digest(ids_bytes(inp["official_ids"]))
        need(prompt_hash == rec["rows"][i - 1]["official_ids_sha256"], "official input identity")
        requests.append(
            {
                "ids": ids,
                "prompt": prompt,
                "cache": cache,
                "frames": frames,
                "preserved": settings["preserved_tokens"],
            }
        )
        public.append(
            {
                "label": label,
                "sampled_ids_sha256": digest(packed),
                "count": n,
                "official_ids_sha256": prompt_hash,
                "native_batch_echoes": n - 1,
                "chat_frames": len(frames),
                "unique_final_eog": True,
            }
        )
        binaries.append(packed)
    projected, build = native_projection(a.native_backends, a.vocab, requests, a.new_output_dir)
    for turn, samples_one, expected in zip(projected, samples, public, strict=True):
        need(
            turn["eog_only_at_end"] is True and turn["frames"] == expected["chat_frames"],
            "projection dimensions",
        )
        piece_rows(log, samples_one, [bytes.fromhex(x) for x in turn["pieces_hex"]])
    for label, packed in zip(("T1", "T2"), binaries, strict=True):
        with (a.new_output_dir / (label + "-sampled.i32")).open("xb") as out:
            out.write(packed)
    return {
        "status": "PASS_TWO_NATURAL_SAMPLED_TRAJECTORIES",
        "turns": public,
        "historical_receipt_sha256": HISTORICAL,
        "historical_manifest_sha256": historical,
        "capture_receipt_sha256": a.capture_sha256,
        "stderr_sha256": native["stderr_sha256"],
        "capture_turn_files_sha256": {
            f"T{i}-{suffix}": sha(a.capture / "raw" / f"T{i}-{suffix}")
            for i in (1, 2)
            for suffix in ("input.json", "result.json", "request.jsonl")
        },
        "protocol_sha256": sha(HERE / "protocol.md"),
        "program_sha256": sha(Path(__file__)),
        "vocabulary_sha256": VOCAB,
        "projection": build,
        "model_forwards": 0,
        "scope": "Contemporary DEBUG trajectories only. Historical sampled IDs remain unobserved.",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("historical", "capture", "vocab", "native-backends", "new-output-dir"):
        ap.add_argument("--" + name, type=Path, required=True)
    ap.add_argument("--capture-sha256", required=True)
    a = ap.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a)
    except Exception as e:
        result = {
            "status": "FAIL_PRESERVED",
            "gate": str(e) if isinstance(e, Gate) else type(e).__name__,
            "capture_receipt_sha256": a.capture_sha256,
        }
    with (a.new_output_dir / "receipt.json").open("x") as out:
        json.dump(result, out, sort_keys=True, indent=2, allow_nan=False)
        out.write("\n")
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
