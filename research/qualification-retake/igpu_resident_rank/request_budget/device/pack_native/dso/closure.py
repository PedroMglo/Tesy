"""Audit the private SONAME with the historical C281 and C292 loader reviewers."""

from pathlib import Path

C281 = "9e553bcfa3dd8889100c8836bc3b873491248567672f93e7859e7f8b76e35116"
C292 = "7b0ca3bcc778f527dfc4cdfab3aaa3f93687045cba5e12d5a74b8310aeb7b670"


def run(server, a, out, original, image, r):
    c, need, sha = server.capture, server.need, server.sha
    name = c.SONAME
    history = c.derive.load(a.c281_closure, C281)
    numeric = c.derive.load(a.c292_closure, C292)
    need(
        history["status"] == "PASS_C281_C291_STATIC_CLOSURE"
        and history["numeric_closure_sha256"] == C292
        and numeric["status"] == "PASS_C292_CAPTURE_STATIC_CLOSURE"
        and history["startup"][name]
        == numeric["startup"][name]
        == {"file": str(original), "sha256": sha(original)},
        "historical C291 closures",
    )
    auth = server.linkage.Authority(c.derive.REPO, a.preflight_dir, c.PREFLIGHT, "C281")
    need(
        sha(auth.exe) == server.SERVER
        and sha(auth.static.LOADER) == history["loader_sha256"]
        and sha(Path("/usr/bin/ldd")) == c.LDD
        and sha(Path("/usr/bin/readelf")) == server.READ_ELF
        and sha(Path(history["manifest"])) == history["manifest_sha256"],
        "historical executable/tools/manifest",
    )
    base = out / "libs"
    base.mkdir(mode=0o700)
    alias = base / name
    alias.symlink_to(image)
    c.aliases(base, {name: str(image)})
    refs = {n: Path(v["file"]) for n, v in history["startup"].items()}
    need(
        len(refs) == 24 and all(sha(p) == history["startup"][n]["sha256"] for n, p in refs.items()),
        "provider evidence",
    )
    refs["server"] = auth.exe
    paths = history["explicit_search"]
    historical_alias = Path(paths[0]) / name
    c.aliases(Path(paths[0]), {name: str(original)})
    need(paths[1:] == auth.arm["native_search"], "historical search path")
    logs = out / "loader"
    logs.mkdir()
    calls = {}

    def query(label, args, env):
        return c.query(logs, label, args, env, calls)

    consumers = [
        n
        for n, p in refs.items()
        if name
        in server.needed(query("dynamic-" + n, ["/usr/bin/readelf", "--wide", "-d", p], c.CLEAN))
    ]
    need(
        set(consumers) == set(history["consumers"]) == server.KNOWN_CONSUMERS | {"server"},
        "four direct consumers",
    )
    search = [str(base), *auth.arm["native_search"]]
    modes = {}
    for mode in ("original", "off", "on"):
        original_mode = mode == "original"
        selected, provider = (historical_alias, original) if original_mode else (alias, image)
        env = auth.static.environment(paths if original_mode else search)
        env["TESY_EXPERT_STORE_MANIFEST"] = history["manifest"]
        if mode == "on":
            env["TESY_PHASE_FD_FILE"] = str(out / "forbidden-journal")
        need(
            not query(mode + "-verify", [auth.static.LOADER, "--verify", auth.exe], env),
            "verify diagnostic",
        )
        reports = {}
        for n in consumers:
            p = refs[n]
            label = mode + "-" + n

            projections = []
            for kind, args in (
                ("-list", [auth.static.LOADER, "--list", p]),
                ("-relocations", ["/usr/bin/ldd", "-r", p]),
            ):
                listed = auth.static.interpret(query(label + kind, args, env))
                actual = server.validate_map(
                    listed, auth.links, selected, provider, entire=n == "server"
                )
                need(
                    actual == history["per_mode"]["on"][n] | {name: str(provider)},
                    "different historical consumer closure",
                )
                if n == "server" and kind == "-list":
                    wrong, other = (alias, image) if original_mode else (historical_alias, original)
                    server.check_wrong_provider(listed, auth.links, wrong, other)
                projections.append(actual)
            need(projections[0] == projections[1], "relocations")
            reports[n] = projections[0]
        modes[mode] = reports
    last = auth.static.interpret(
        query(
            "original-end", [auth.static.LOADER, "--list", auth.exe], auth.static.environment(paths)
        )
    )
    need(
        server.validate_map(last, auth.links, historical_alias, original, entire=True)
        == modes["original"]["server"],
        "original end",
    )
    need(
        len(calls) == 53
        and modes["off"] == modes["on"]
        and not (out / "forbidden-journal").exists(),
        "static family",
    )
    startup = history["startup"] | {name: {"file": str(image), "sha256": sha(image)}}
    nmap = numeric["startup"] | {name: startup[name]}
    need(
        len(nmap) == 18 and all(sha(Path(v["file"])) == v["sha256"] for v in nmap.values()),
        "numeric providers",
    )
    exe = Path(numeric["executable"])
    need(sha(exe) == c.CAPTURE, "C292 executable")
    spec = auth.static.environment([str(base), *numeric["explicit_search"][1:]])
    q = {}
    for label, args in (
        ("C292-list", [auth.static.LOADER, "--list", exe]),
        ("C292-relocations", ["/usr/bin/ldd", "-r", exe]),
    ):
        listed = auth.static.interpret(c.query(logs, label, args, spec, q))
        need(
            listed.keys() == nmap.keys()
            and listed[name] == alias
            and all(str(v.resolve(strict=True)) == nmap[n]["file"] for n, v in listed.items()),
            "C292 resolves unexpected DSO",
        )
    c.aliases(base, {name: str(image)})
    auth.recheck()
    r.update(
        queries=calls,
        capture_queries=q,
        consumers=consumers,
        per_mode=modes,
        startup=startup,
        capture_startup=nmap,
        explicit_search=search,
        static_preflight_sha256=c.PREFLIGHT,
        c281_closure_sha256=C281,
        c292_closure_sha256=C292,
        manifest_sha256=history["manifest_sha256"],
        index_sha256=history["index_sha256"],
    )
