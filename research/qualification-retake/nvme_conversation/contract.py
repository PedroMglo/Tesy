"""Historical C281 workload and contemporary runtime for a two-turn qualification."""

import hashlib
import json
import os
import socket
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path[:0] = [
    str(REPO / "tools"),
    str(HERE.parent),
    str(HERE.parent / "nvme_r0_gate"),
    str(HERE.parent / "cuda35"),
    str(HERE.parent / "rows153"),
]
import elf_resolution as elf  # noqa: E402
from prepare import MODEL_SHA, admit, check, git, load  # noqa: E402
from run_bounded import file_identity, sha256  # noqa: E402

C281 = elf.C281
DATE = "2026-10-05"
PORT = 18442
CAP = 20 * 2**30
CLIENT_SHA = "2cca03a7262a0715338ffd73e7ec3ca4d129dfa5f03760fe36971b51d46d31b9"


def source_digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def ids_hash(ids):
    check(
        isinstance(ids, list) and all(type(i) is int and i >= 0 for i in ids),
        "official IDs invalid",
    )
    return hashlib.sha256(struct.pack(f"<{len(ids)}i", *ids)).hexdigest()


def owned_listener(pid, port):
    """Match the unique bound IPv4 listener to both an fd and the recorded process namespace."""
    check(
        os.stat("/proc/self/ns/net").st_ino == os.stat(f"/proc/{pid}/ns/net").st_ino,
        "HTTP network namespace differs",
    )
    target = f"0100007F:{port:04X}"
    inodes = []
    for row in Path(f"/proc/{pid}/net/tcp").read_text().splitlines()[1:]:
        fields = row.split()
        if fields[1] == target and fields[3] == "0A":
            inodes.append(fields[9])
    check(len(inodes) == 1, "unique loopback LISTEN socket absent")
    files = set()
    for fd in Path(f"/proc/{pid}/fd").iterdir():
        try:
            files.add(os.readlink(fd))
        except FileNotFoundError:
            continue
    check(f"socket:[{inodes[0]}]" in files, "HTTP listener belongs to another PID")
    return inodes[0]


def idle_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", PORT))


def sources():
    config = elf.pinned(C281 / "c281-r0-persistent-config.json", elf.CONFIG)
    manifest = elf.pinned(C281 / "runtime-manifest.json", elf.MANIFEST)
    elf.pinned(C281 / "protocols/c281-r0-persistent.json", elf.PROTOCOL)
    frozen = load(C281 / "freeze.json")["source_sha256"]
    historical = elf.pinned(
        C281 / "protocol.json", frozen["results/c281-persistent-r0-runtime-20261005/protocol.json"]
    )
    check(
        sha256(REPO / "tools/optin_integration_client.py") == CLIENT_SHA
        and [t["id"] for t in historical["tasks"]] == ["c112-code", "c112-repeat"],
        "client or workload differs",
    )
    run = load(C281 / "command.json")
    cmd = run["monitor_command"]
    cmd = cmd[cmd.index("--") + 1 :]
    from c143_slots40_optin import configured_command

    check(cmd == configured_command(config, PORT, DATE), "C281 actual command differs")
    rows = load(C281 / "compact.json")["rows"]
    for i, row in enumerate(rows, 1):
        raw = Path(run["session"]) / "raw" / f"T{i}-input.json"
        check(
            sha256(raw) == row["input_raw_sha256"]
            and ids_hash(load(raw)["official_ids"]) == row["official_ids_i32le_sha256"],
            "historical official IDs",
        )
    evidence = load(HERE.parent / "elf-evidence/receipt.json")
    expected = {r["load_name"]: r for r in evidence["selected_frozen_and_unpinned"]}
    actual, aux = elf.selections(elf.command("/usr/bin/ldd", cmd[0]))
    check(
        set(actual) == set(expected)
        and len(actual) == 23
        and aux == evidence["unfrozen_auxiliary"],
        "ELF startup set differs",
    )
    check(
        {n for n, r in expected.items() if r["status"] == "MISMATCH"}
        == {"libcuda.so.1", "libgcc_s.so.1", "libstdc++.so.6", "libgomp.so.1"},
        "unknown ELF drift",
    )
    refs = {}
    for name, path in actual.items():
        row = expected[name]
        check(
            path
            and path.name == row["resolved_file"]
            and elf.stable_hash(path) == row["resolved_sha256"],
            "selected runtime changed: " + name,
        )
        refs[name] = {"path": str(path), "sha256": row["resolved_sha256"]}
    check(sha256(cmd[0]) == manifest["binary_sha256"], "server digest")
    backend = Path(config["backend_root"]).resolve()
    check(
        git(backend, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()
        == [manifest["backend_head"], manifest["backend_tree"]]
        and not git(backend, "status", "--porcelain"),
        "dirty backend",
    )
    return dict(
        official_ids=[r["official_ids_i32le_sha256"] for r in rows],
        historical_inputs=[r["input_raw_sha256"] for r in rows],
        server_command=cmd,
        binary_sha256=manifest["binary_sha256"],
        explicit_env=config["explicit_env"],
        backend=str(backend),
        dso=refs,
        parallel_runtime=manifest["parallel_runtime"]
        | {"libraries_sha256": {refs["libgomp.so.1"]["path"]: refs["libgomp.so.1"]["sha256"]}},
        model_sha256=MODEL_SHA,
        session_date=DATE,
        port=PORT,
        cap_bytes=CAP,
        protocol_sha256=sha256(HERE / "protocol.md"),
        historical_workload_sha256=sha256(C281 / "protocol.json"),
    )


def placement(window, placement_path):
    policy = load(window / "resource-policy.json")
    w = load(window / "receipt.json")
    admit(w, policy, sha256(window / "resource-policy.json"), "E20_R0")
    record = load(placement_path)
    check(
        sha256(placement_path)
        == load(HERE.parent / "nvme_placement/receipt.json")["raw_receipt_sha256"]
        and record["destination_direct_reread"]["sha256"] == MODEL_SHA,
        "placement identity",
    )
    p = Path(record["launcher_path"])
    ident = file_identity(p)
    check(
        p.samefile(record["working_copy"])
        and not p.samefile(record["original"])
        and [ident[k] for k in ("dev", "inode", "size_bytes", "mtime_ns", "ctime_ns")]
        == w["selected_stat"],
        "GGUF relocation",
    )
    return policy, ident
