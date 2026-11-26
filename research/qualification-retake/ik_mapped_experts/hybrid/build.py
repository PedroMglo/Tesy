"""Compile just the two shared libraries in a new scope after a qualified dry run."""

import argparse
import hashlib
import json
import os
import re
import runpy
import shutil
import signal
import subprocess
import time
from pathlib import Path

C = runpy.run_path(str(Path(__file__).with_name('configure.py')))
GIB = C['GIB']
check = C['require']
sha = C['checksum']


def configure_for_receipt(expected):
    path = Path(__file__).with_name("configure.py")
    if sha(path) == expected:
        return C
    check(
        expected == "5786e2c6618981d33f819194314f3e2bf6231eea638836e3606def74c4913702",
        "unknown configure source",
    )
    # The completed SM89 experiment used this Git blob. Verify its exact bytes before loading it.
    original = subprocess.check_output(
        ["git", "-C", path.parent, "cat-file", "blob", "ff313f422ca34403e8c855b42fa0948d7bead8aa"],
        timeout=10,
    )
    check(hashlib.sha256(original).hexdigest() == expected, "archived configure source")
    namespace = {"__file__": str(path), "__name__": "tesy_frozen_configure"}
    exec(compile(original, str(path), "exec"), namespace)
    return namespace


def group(unit):
    relative = next(
        line[3:]
        for line in Path("/proc/self/cgroup").read_text().splitlines()
        if line.startswith("0::")
    )
    path = Path('/sys/fs/cgroup') / relative.lstrip('/')
    check(
        unit == path.name and unit.startswith("tesy-ik-hybrid-build-") and unit.endswith(".scope"),
        "wrong scope",
    )
    check((path/'memory.max').read_text().strip() == str(6*GIB), 'memory cap')
    check((path/'memory.swap.max').read_text().strip() == '0', 'swap cap')
    return path


def memory_events(cg):
    return {
        k: int(v)
        for k, v in (line.split() for line in (cg / "memory.events").read_text().splitlines())
    }


def boxed(command, out, cfg, log, env=None, cg=None, timeout=90):
    # Absolute Ninja paths are sealed to the configured tree; bind a private copy there.
    mount = ['/usr/bin/bwrap','--die-with-parent','--unshare-net','--ro-bind','/','/',
             '--dev','/dev','--proc','/proc','--bind',str(out),str(out),
             '--bind',str(out/'objects'),str(cfg/'objects'),'--',*map(str, command)]
    settings = {'PATH':'/usr/bin:/bin','LC_ALL':'C','HOME':str(out/'tmp'),'TMPDIR':str(out/'tmp'),
                'CUDA_VISIBLE_DEVICES':'','GIT_OPTIONAL_LOCKS':'0'} | (env or {})
    start = time.monotonic()
    events = memory_events(cg)
    last_size = 0
    with log.open('xb') as f:
        child = subprocess.Popen(
            mount, stdout=f, stderr=subprocess.STDOUT, env=settings, start_new_session=True
        )
        try:
            while True:
                check(time.monotonic() - start < timeout, 'time limit')
                check(shutil.disk_usage(out).free >= 11*GIB, 'free disk limit')
                last_size = max(last_size, C['size'](out))
                check(last_size < 8*GIB, 'build tree size limit')
                check(int((cg/'memory.swap.current').read_text()) == 0, 'swap')
                curr = memory_events(cg)
                check(all(curr[k] == events[k] for k in ('oom','oom_kill','max')), 'memory stop')
                if child.poll() is not None:
                    check(child.returncode == 0, f'{log.name} returned {child.returncode}')
                    break
                try:
                    child.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    continue
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
    return {'seconds':round(time.monotonic()-start,3), 'output_peak_sampled_bytes':last_size}


def perform(args, out):
    cfg = args.configure_dir.resolve()
    check(sha(cfg/'receipt.json') == args.configure_sha256, 'configure receipt')
    r = json.loads((cfg/'receipt.json').read_bytes())
    check(
        r["status"] == "PASS_IK_SM89_CONFIGURE_ONLY" and r["output"] == str(cfg),
        "qualified configure",
    )
    src = Path(r['source'])
    configured = configure_for_receipt(r["script_sha256"])
    configured["pin"](src)
    check(sha(Path(__file__).with_name('protocol.md')) == r['protocol_sha256'], 'protocol drift')
    for name, digest in (r['logs_sha256'] | r['tools_sha256']).items():
        check(sha(cfg/name) == digest, name)
    p = configured["providers"](args.env49_map)
    check(p == r['providers'], 'provider identity')
    cg = group(args.unit)
    cfg_obj = cfg/'objects'
    for name, digest in r['plan_sha256'].items():
        check(sha(cfg_obj/name) == digest, name)
    check(all('CompilerIdCUDA' in path.parts for path in cfg_obj.rglob('*.o'))
          and not (cfg_obj/'.ninja_log').exists(), 'config contains project build products')
    shutil.copytree(cfg_obj, out/'objects', symlinks=True)
    (out/'tmp').mkdir(mode=0o700)
    build = boxed(
        ["/usr/bin/ninja", "-C", cfg_obj, "-j2", "llama"],
        out,
        cfg,
        out / "build.log",
        cg=cg,
        timeout=5400,
    )
    for name, digest in r['plan_sha256'].items():
        check(
            sha(cfg_obj / name) == digest and sha(out / "objects" / name) == digest,
            f"plan changed {name}",
        )
    libs = [out/'objects/ggml/src/libggml.so',out/'objects/src/libllama.so']
    desc = json.loads(args.env49_map.read_bytes())
    ddir = Path(desc['driver_dir'])
    for soname, resolved in desc['driver_aliases'].items():
        check((ddir/soname).resolve() == Path(resolved), soname)
    libpath = ":".join(
        map(str, [libs[0].parent, libs[1].parent, ddir, configured["TOOLKIT"] / "lib64"])
    )
    closure = {}
    for lib in libs:
        log = out/f'{lib.name}.ldd-r'
        boxed(['/usr/bin/ldd','-r',lib],out,cfg,log,env={'LD_LIBRARY_PATH':libpath},cg=cg)
        content = log.read_text()
        check(
            "undefined symbol" not in content
            and "not found" not in content
            and "/stubs/" not in content,
            "loader",
        )
        linked = {
            k: Path(v).resolve() for k, v in re.findall(r"^\s*(\S+) => (/\S+) \(0x", content, re.M)
        }
        for soname in ('libcudart.so.13','libcublas.so.13','libcublasLt.so.13','libcuda.so.1'):
            check(str(linked.get(soname)) == p[soname]['path'], f'{lib.name} {soname}')
        if lib == libs[1]:
            check(linked.get('libggml.so') == libs[0], 'wrong ggml')
        absolute = {Path(v).resolve() for v in re.findall(r'^\s*(/\S+) \(0x',content,re.M)}
        closure[lib.name] = {str(path):sha(path) for path in sorted(set(linked.values())|absolute)}
        symbols = out/f'{lib.name}.symbols'
        boxed(['/usr/bin/nm','-D','--defined-only',lib],out,cfg,symbols,cg=cg)
        sym = 'ggml_backend_cuda_init' if lib == libs[0] else 'llama_memory_breakdown'
        check(re.search(rf'\b{sym}$',symbols.read_text(),re.M), f'missing {sym}')
    check(
        all(
            closure[lib.name].get(p[name]["path"]) == p[name]["sha256"]
            for lib in libs
            for name in ("libcudart.so.13", "libcublas.so.13", "libcublasLt.so.13", "libcuda.so.1")
        ),
        "provider hash",
    )
    return {
        "status": "PASS_IK_SM89_LINK_ONLY",
        "build": build,
        "libraries": {str(x.relative_to(out)): sha(x) for x in libs},
        "closure": closure,
        "configure_sha256": args.configure_sha256,
        "script_sha256": sha(__file__),
        "cgroup_memory_peak_bytes": int((cg / "memory.peak").read_text()),
        "model_loads": 0,
        "gpu_dispatches": 0,
    }


def main():
    a = argparse.ArgumentParser()
    a.add_argument('--configure-dir',required=True,type=Path)
    a.add_argument('--configure-sha256',required=True)
    a.add_argument('--env49-map',required=True,type=Path)
    a.add_argument('--unit',required=True)
    a.add_argument('--new-output-dir',required=True,type=Path)
    args = a.parse_args()
    out = args.new_output_dir.absolute()
    out.mkdir(mode=0o700)
    try:
        result = perform(args,out)
    except Exception as error:
        C['write'](out/'receipt.json',{'status':'FAIL_PRESERVED','error':str(error),
                                       'configure_sha256':args.configure_sha256,'script_sha256':sha(__file__)})
        raise
    C['write'](out/'receipt.json',result)
    print(result['status'],sha(out/'receipt.json'))


if __name__ == '__main__':
    main()
