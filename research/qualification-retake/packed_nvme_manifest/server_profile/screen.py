"""C281 loader and consumer relocations with the single C291 store library, without main."""

import argparse
import datetime as dt
import json
import os
import re
import signal
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "phase_fd/integrated/profile"))
import linkage  # noqa: E402

capture = linkage.load_module(HERE.parent / "capture_profile/screen.py", "c292_capture_static")
need, sha = capture.need, capture.sha
PROTOCOL = "63c325d2c20d81e2a89badf712a05a9d509d03362542d48603749594c52684f8"
READ_ELF = "20f4971b177980026114be33ed5ce3814aeeac3c12ba8a329b9c2ef3b42cf20f"
SERVER = "054e983528d35731e2dc6222f1418f2f08120ef83e0c5f2a8db11805dd38effa"
C281 = "cb191e31c2e3ee547a01228065a3c4253bdb312dd1e561d361f75365f065356a"
C292 = "f7a5f270e427b8b9390b17ae1a49b2d154a57a822b9afc0ab1c1039f0641b9c7"
CLOSURE = "7b0ca3bcc778f527dfc4cdfab3aaa3f93687045cba5e12d5a74b8310aeb7b670"
KNOWN_CONSUMERS = {"libllama-common.so.0", "libmtmd.so.0", "libllama-server-impl.so"}
SONAME = capture.SONAME


def validate_map(listed, allowed, alias, image, *, entire):
    need(SONAME in listed and len(allowed) == 24, "server closure size/provider")
    if entire:
        need(set(listed) == set(allowed), "unexpected full-program providers")
    else:
        need(set(listed) <= set(allowed), "foreign isolated-consumer provider")
    result = {}
    for name, path in listed.items():
        real = path.resolve(strict=True)
        if name == SONAME:
            need(path == alias and real == image, "wrong libllama provider")
        else:
            need(str(real) == allowed[name][1], "provider differs: " + name)
        result[name] = str(real)
    return result


def check_wrong_provider(listed, allowed, alias, image):
    try:
        validate_map(listed, allowed, alias, image, entire=True)
    except ValueError as exc:
        need(str(exc) == "wrong libllama provider", "unexpected negative-control reason")
    else:
        raise ValueError("foreign libllama accepted")


def needed(text):
    libs = []
    for line in text.splitlines():
        if "(NEEDED)" not in line:
            continue
        m = re.fullmatch(r"\s*0x[0-9a-f]+\s+\(NEEDED\)\s+Shared library: \[([^]/\s]+)\]", line)
        need(m and m[1] not in libs, "ambiguous DT_NEEDED")
        libs.append(m[1])
    return libs


def family(a, out, row):
    need(
        sha(HERE / "protocol.md") == PROTOCOL
        and capture.git("rev-parse", "HEAD") == a.commit
        and not capture.git("status", "--porcelain"),
        "clean measurement checkout",
    )
    row.update(
        commit=a.commit,
        tree=capture.git("rev-parse", "HEAD^{tree}"),
        protocol_sha256=PROTOCOL,
        source_sha256=sha(Path(__file__)),
        queries={},
        initial_scope=capture.scope(a.unit),
    )
    a.derived_sha256 = capture.DERIVED_R02
    a.constructor_sha256 = capture.CHAINS[a.derived_sha256]
    kr = capture.derive.load(a.c281_receipt, C281)
    pair = capture.derive.load(a.c292_receipt, C292)
    need(
        kr["status"] == "PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY"
        and kr["model_launches"] == 1
        and pair["status"] == "PASS_SELECTED_C292_NVME_PAIR"
        and pair["model_launch_receipts"] == 2
        and pair["closure_sha256"] == CLOSURE
        and [r["status"] for r in pair["arms"]] == ["PASS_C292_OFF", "PASS_C292_ON"],
        "C281 and C292 receipts",
    )
    for arm in pair["arms"]:
        rr = capture.derive.load(
            a.c292_receipt.parent / arm["mode"] / "receipt.json", arm["receipt_sha256"]
        )
        need(rr["status"] == arm["status"] and rr["child_exit"] == 0, "numeric arm authority")
    manifest, metadata = capture.metadata(a)
    auth = linkage.Authority(capture.derive.REPO, a.preflight_dir, capture.PREFLIGHT, "C281")
    need(
        sha(auth.exe) == SERVER
        and sha(auth.static.LOADER) == auth.files[str(auth.static.LOADER.resolve())]["sha256"]
        and sha(Path("/usr/bin/ldd")) == capture.LDD
        and sha(Path("/usr/bin/readelf")) == READ_ELF,
        "server or tools changed",
    )
    _, image, _ = capture.historical(a)
    orig_alias = Path(auth.links[SONAME][0])
    original = Path(auth.links[SONAME][1])
    need(sha(original) == capture.C269 and len(auth.links) == 24, "original C269 server library")
    private = out / "libs"
    private.mkdir(mode=0o700)
    alias = private / SONAME
    alias.symlink_to(image)
    capture.aliases(private, {SONAME: str(image)})
    search = [str(private), *auth.arm["native_search"]]
    refs = {n: Path(v[1]) for n, v in auth.links.items()}
    refs["server"] = auth.exe
    row["consumers"] = []
    for name, p in refs.items():
        data = capture.query(
            out,
            "dynamic-" + name,
            ["/usr/bin/readelf", "--wide", "-d", p],
            capture.CLEAN,
            row["queries"],
        )
        if SONAME in needed(data):
            row["consumers"].append(name)
    need(KNOWN_CONSUMERS <= set(row["consumers"]), "missing known direct C281 consumer")
    modes = {}
    for mode in ("original", "off", "on"):
        original_mode = mode == "original"
        selected_alias, selected_image = (orig_alias, original) if original_mode else (alias, image)
        env = auth.static.environment(auth.arm["native_search"] if original_mode else search)
        if mode == "on":
            env["TESY_EXPERT_STORE_MANIFEST"] = str(manifest)
        need(
            not capture.query(
                out,
                mode + "-verify",
                [auth.static.LOADER, "--verify", auth.exe],
                env,
                row["queries"],
            ),
            "unexpected --verify output",
        )
        reports = {}
        for root in dict.fromkeys(["server", *row["consumers"]]):
            program = refs[root]

            label = mode + "-" + root
            listed = auth.static.interpret(
                capture.query(
                    out,
                    label + "-list",
                    [auth.static.LOADER, "--list", program],
                    env,
                    row["queries"],
                )
            )
            resolved = validate_map(
                listed, auth.links, selected_alias, selected_image, entire=root == "server"
            )
            reloc = auth.static.interpret(
                capture.query(
                    out,
                    label + "-relocations",
                    ["/usr/bin/ldd", "-r", program],
                    env,
                    row["queries"],
                )
            )
            need(
                validate_map(
                    reloc, auth.links, selected_alias, selected_image, entire=root == "server"
                )
                == resolved,
                "relocated image differs from listing",
            )
            if root == "server":
                check_wrong_provider(
                    listed,
                    auth.links,
                    alias if original_mode else orig_alias,
                    image if original_mode else original,
                )
            reports[root] = resolved
        modes[mode] = reports
    need(modes["off"] == modes["on"], "OFF and ON map differs")
    capture.metadata(a)
    capture.aliases(private, {SONAME: str(image)})
    auth.recheck()
    need(
        sha(auth.exe) == SERVER and sha(original) == capture.C269 and sha(image) == capture.C291,
        "terminal image identity",
    )
    terminal = auth.static.interpret(
        capture.query(
            out,
            "original-end",
            [auth.static.LOADER, "--list", auth.exe],
            auth.static.environment(auth.arm["native_search"]),
            row["queries"],
        )
    )
    need(
        validate_map(terminal, auth.links, orig_alias, original, entire=True)
        == modes["original"]["server"],
        "terminal reference changed",
    )
    startup = {
        k: {"file": v, "sha256": capture.C291 if k == SONAME else auth.files[v]["sha256"]}
        for k, v in modes["on"]["server"].items()
    }
    row.update(
        status="PASS_C281_C291_STATIC_CLOSURE",
        original_receipt_sha256=C281,
        numerical_pair_sha256=C292,
        numeric_closure_sha256=CLOSURE,
        startup=startup,
        explicit_search=search,
        server=str(auth.exe),
        binary_sha256=SERVER,
        library_sha256=capture.C291,
        original_library_sha256=capture.C269,
        per_mode=modes,
        original_and_candidate_rejected_as_each_other=True,
        preflight_sha256=capture.PREFLIGHT,
        static_map_sha256=auth.pre["static_map_sha256"],
        driver_deployment=auth.origin.COMMIT,
        kernel=auth.pre["kernel"],
        manifest=str(manifest),
        manifest_sha256=metadata["manifest_sha256"],
        index_sha256=metadata["index_sha256"],
        derived_sha256=a.derived_sha256,
        constructor_sha256=a.constructor_sha256,
        loader_sha256=sha(auth.static.LOADER),
        ldd_sha256=capture.LDD,
        readelf_sha256=READ_ELF,
        final_scope=capture.scope(a.unit),
        model_processes=0,
        transformer_forwards=0,
        backend_enumerations=0,
        server_processes=0,
        payload_read_bytes=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in (
        "preflight-dir",
        "c281-receipt",
        "c292-receipt",
        "derived-dir",
        "constructor-receipt",
        "bin-dir",
        "new-output-dir",
    ):
        p.add_argument("--" + key, type=Path, required=True)
    for key in ("commit", "unit"):
        p.add_argument("--" + key, required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    start = time.monotonic_ns()
    row = {"status": "FAIL_PRESERVED", "started_utc": dt.datetime.now(dt.UTC).isoformat()}

    def stop(*_):
        raise TimeoutError("120 s static closure")

    signal.signal(signal.SIGALRM, stop)
    signal.alarm(120)
    try:
        family(a, out, row)
        need(
            sum(f.stat().st_size for f in out.iterdir() if f.is_file())
            + len(json.dumps(row))
            + 65536
            < 8 << 20,
            "raw output budget",
        )
    except Exception as e:
        row.update(status="FAIL_PRESERVED", reason=f"{type(e).__name__}: {e}")
    finally:
        signal.alarm(0)
    row.update(
        elapsed_ns=time.monotonic_ns() - start, finished_utc=dt.datetime.now(dt.UTC).isoformat()
    )
    capture.derive.save(out / "receipt.json", row)
    print(row["status"])
    return int(row["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
