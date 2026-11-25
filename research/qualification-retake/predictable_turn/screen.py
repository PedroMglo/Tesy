"""Bound the contiguous target prefix knowable before the next user message."""
import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "CUDA_VISIBLE_DEVICES": ""}
CASES = ("A", "Ω", "7")


def require(condition, gate):
    if not condition:
        raise ValueError(gate)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def document(path):
    return json.loads(path.read_bytes())


def verified(path, expected):
    data = path.read_bytes()
    require(sha(data) == expected, "source identity: " + path.name)
    return data


def run(argv, data=b""):
    return subprocess.run(argv, input=data, capture_output=True, env=ENV, timeout=10, check=True).stdout


def frame(data):
    return struct.pack("<I", len(data)) + data


def frames(data):
    result = []
    while data:
        require(len(data) >= 4, "length prefix")
        n, = struct.unpack_from("<I", data)
        require(0 < n <= len(data)-4, "frame length")
        result.append(data[4:4+n])
        data = data[4+n:]
    return result


def prefix(rows):
    return next((i for i, items in enumerate(zip(*rows)) if len(set(items)) != 1), min(map(len, rows)))


def geometry(log, cached, total):
    tasks = list(re.finditer(rb"(?m)^\S+ I slot launch_slot_: id +0 \| task (\d+) \| processing task, is_child = 0$", log))
    require(len(tasks) == 2, "two single-slot admissions")
    task = tasks[-1].group(1)
    region = log[tasks[-1].end():]
    sample = re.search(rb"(?m)^\S+ D slot process_toke: id +0 \| task "+task+rb" \| n_decoded = 1,", region)
    require(sample is not None, "first sample")
    window = region[:sample.start()]
    require(b"retrying with smaller batch size" not in window, "retry")
    sequence = []
    for line in window.splitlines():
        if b"main/do_checkpoint =" in line:
            event = re.fullmatch(rb"\S+ D slot +operator\(\): id +0 \| task "+task+rb" \| main/do_checkpoint = no, pos_min = 0, pos_max = (\d+)", line)
            require(event is not None, "position gate")
            sequence.append(int(event.group(1))+1)
        if b"n_batch (effective)" in line:
            require(re.fullmatch(rb"\S+ D srv +decode: n_batch \(effective\) = 256, off = 0", line), "batch offset or capacity")
            sequence.append("decode")
    require(len(sequence) == 4 and sequence[1::2] == ["decode", "decode"], "two position/decode pairs")
    start, split = sequence[::2]
    require(start == cached and start < split < total, "position boundaries")
    return [split-start, total-split]


def providers(binary, authority):
    selected = {}
    for lib, path in re.findall(r"^\s*(lib(?:llama|ggml)[^ ]+) => (\S+) ", run(["/usr/bin/ldd", binary]).decode(), re.M):
        path = Path(path).resolve()
        require(path.name in authority, "unknown loader provider")
        verified(path, authority[path.name])
        selected[lib] = authority[path.name]
    require("libllama.so.0" in selected and "libggml-base.so.0" in selected, "required libraries")
    return selected


def screen(args):
    proof = document(BASE/"history_lookup/native_ids/evidence/verified.json")
    vocab_ref = document(BASE/"aster_vocab/attempt-03/receipt.json")
    render_ref = document(BASE/"aster_template/attempt-01/receipt.json")
    verified(args.capture/"receipt.json", proof["capture_receipt_sha256"])
    raw = args.capture/"raw"
    inputs = {}
    for name, digest in proof["capture_turn_files_sha256"].items():
        data = verified(raw/name, digest)
        if name.endswith(".json"):
            inputs[name] = json.loads(data)
    log, = raw.glob("*.stderr")
    source_log = verified(log, proof["stderr_sha256"])
    data = inputs["T2-input.json"]
    messages = data["messages"]
    require([m["role"] for m in messages] == ["user", "assistant", "user"] and
            messages[1]["content"] == inputs["T1-result.json"]["message"]["content"], "T1 history")
    kwargs = data["template_kwargs"]
    require(kwargs == {"reasoning_effort":"medium", "tesy_template_date":"2026-10-05"}, "template options")
    vocab = args.vocab_dir/"vocab.gguf"
    tok = args.vocab_dir/"C269"
    render = args.renderer_dir/"C269"
    verified(vocab, vocab_ref["vocab_copy_sha256"])
    for binary, digest in [(tok, vocab_ref["executables_sha256"]["C269"]), (render, render_ref["compilations"]["C269"]["binary_sha256"])]:
        verified(binary, digest)
    dsos = {name:providers(exe, proof["projection"]["provider_sha256"]) for name, exe in [("render",render),("tokenize",tok)]}
    require("libllama-common.so.0" in dsos["render"], "renderer library")
    tokenize = [tok, "--tokenize", vocab]
    template, = frames(run(tokenize))
    require(sha(template) == render_ref["original_template_sha256"], "embedded template")

    def token_rows(prompts):
        tmpl, *rows = frames(run(tokenize, b"".join(frame(p) for p in prompts)))
        require(tmpl == template and len(rows) == len(prompts), "tokenizer ABI")
        return [struct.unpack("<%di" % (len(row)//4), row) for row in rows]

    with tempfile.TemporaryDirectory(dir=args.new_output_dir) as td:
        path = Path(td)/"template.jinja"
        path.write_bytes(template)

        def prompt(content):
            turns = [*messages[:-1], {"role":"user", "content":content}]
            stdin = b"".join(frame(m[k].encode()) for m in turns for k in ("role","content"))
            return run([render, path, kwargs["tesy_template_date"]], stdin)

        reference = prompt(messages[-1]["content"])
        require(reference == data["rendered_prompt"].encode(), "official prompt")
        observed, = token_rows([reference])
        require(list(observed) == data["official_ids"] == inputs["T2-result.json"]["official_ids"], "official IDs")
        variants = token_rows([prompt(content) for content in CASES])
    timing = inputs["T2-result.json"]["timings"]
    cached = timing["cache_n"]
    calls = geometry(source_log, cached, len(observed))
    require((len(observed), cached, timing["prompt_n"], calls) == (2197, 2044, 153, [5,148]), "observed geometry")
    limit = max(0, prefix([observed, *variants])-cached)
    sizes = [5,32,32,32,32,20]
    end = 0
    complete = []
    for size in sizes:
        end += size
        if end <= limit:
            complete.append(size)
    return {"status":"PASS_PREFIX_BOUND", "decision_full_148_tiles":"NO_GO" if limit < 37 else "INCONCLUSIVE",
            "capture_receipt_sha256":proof["capture_receipt_sha256"], "program_sha256":sha(Path(__file__).read_bytes()),
            "protocol_sha256":sha((HERE/"protocol.md").read_bytes()), "vocabulary_sha256":vocab_ref["vocab_copy_sha256"],
            "providers":dsos, "official_ids":len(observed), "official_render_bytes":len(reference),
            "official_render_sha256":sha(reference), "cache_n":cached, "observed_outer_calls":calls,
            "assumed_inner_tiles_of_148":sizes[1:], "alternate_counts":list(map(len,variants)),
            "pairwise_prefix_with_official":[prefix([observed,row]) for row in variants],
            "shared_input_prefix":prefix([observed,*variants]), "new_positions_upper_bound":limit,
            "complete_initial_groups_within_bound":complete, "gpu_forwards":0}


def main():
    parser = argparse.ArgumentParser()
    for name in ("capture","vocab-dir","renderer-dir","new-output-dir"):
        parser.add_argument("--"+name, required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir(exist_ok=False)
    dest = args.new_output_dir/"receipt.json"
    try:
        result = screen(args)
    except Exception as exc:
        dest.write_text(json.dumps({"status":"FAIL", "gate":str(exc)}, indent=2)+"\n")
        raise
    dest.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")


if __name__ == "__main__":
    main()
