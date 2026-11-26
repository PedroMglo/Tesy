"""Configure only; project compilation is a separate, explicitly admitted command."""

import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

REV = '7a5d90009b7ae55d3239cdd33244977c4eb10ff6'
TREE = 'a1706c85dc11d32b0fc34e20d699066a88b56201'
TOOLKIT = Path('/usr/local/cuda-13.3')
ENV49 = '7e9d0efb4c9bac6ef88d0de0003e8643fc14f4f9942c72a8101e2c166b8b1729'
GIB = 1 << 30
PLAN_FILES = ('CMakeCache.txt', 'build.ninja', 'CMakeFiles/rules.ninja', 'compile_commands.json')


def checksum(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def require(ok, error):
    if not ok:
        raise ValueError(error)


def pin(src):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(src), *args], text=True).strip()
    require((git('rev-parse', 'HEAD'), git('rev-parse', 'HEAD^{tree}')) == (REV, TREE), 'ik revision')
    require(not git('status', '--porcelain', '--untracked-files=all'), 'ik tree dirty')


def size(root):
    total = 0
    for folder, _, files in os.walk(root):
        for name in files:
            try:
                total += (Path(folder) / name).lstat().st_size
            except FileNotFoundError:
                pass  # Compiler temporaries can disappear between enumeration and stat.
    return total


def limited(out, log, command, seconds, space):
    env = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'HOME': str(out / 'tmp'),
           'TMPDIR': str(out / 'tmp'), 'CUDA_VISIBLE_DEVICES': '', 'GIT_OPTIONAL_LOCKS': '0'}
    box = ['/usr/bin/bwrap', '--die-with-parent', '--unshare-net', '--ro-bind', '/', '/',
           '--dev', '/dev', '--proc', '/proc', '--bind', str(out), str(out), '--', *map(str, command)]
    start = time.monotonic()
    with log.open('xb') as f:
        proc = subprocess.Popen(box, env=env, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while proc.poll() is None:
                require(time.monotonic() - start < seconds, 'wall limit')
                require(size(out) < space and shutil.disk_usage(out).free >= 11 * GIB, 'disk limit')
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    continue
            require(proc.returncode == 0, f'{log.name} returned {proc.returncode}')
            require(size(out) < space and shutil.disk_usage(out).free >= 11 * GIB, 'disk final')
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
    return round(time.monotonic() - start, 3)


def providers(map_path):
    require(checksum(map_path) == ENV49, 'ENV49 map integrity')
    m = json.loads(map_path.read_bytes())
    selected = dict(m['driver_aliases'])
    for name in ('libcublas.so.13', 'libcublasLt.so.13', 'libcudart.so.13'):
        selected[name] = m['arms']['C281']['links'][name][1]
    report = {}
    for name, path in selected.items():
        st = Path(path).stat()
        sealed = m['files'][path]
        require([st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns] ==
                [sealed[k] for k in ('dev', 'ino', 'size', 'mtime_ns', 'ctime_ns')], f'provider drift {name}')
        report[name] = {'path': path, **sealed}
    return report


def configure(src, out, map_path):
    pin(src)
    p = providers(map_path)
    cubin = TOOLKIT / 'bin/nvcc'
    args = [
        '/usr/bin/cmake', '-S', src, '-B', out / 'objects', '-G', 'Ninja',
        '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_C_COMPILER=/usr/bin/gcc-15',
        '-DCMAKE_CXX_COMPILER=/usr/bin/g++-15', '-DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++-15',
        f'-DCMAKE_CUDA_COMPILER={cubin}', f'-DCUDAToolkit_ROOT={TOOLKIT}',
        f'-DCUDA_cuda_driver_LIBRARY={TOOLKIT}/lib64/stubs/libcuda.so',
        '-DCMAKE_CUDA_ARCHITECTURES=89-real', '-DCMAKE_SKIP_RPATH=ON',
        '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', '-DFETCHCONTENT_FULLY_DISCONNECTED=ON',
        '-DBUILD_SHARED_LIBS=ON', '-DGGML_NATIVE=ON', '-DGGML_CUDA=ON', '-DGGML_CCACHE=OFF',
        '-DGGML_CUDA_FA_ALL_QUANTS=OFF', '-DGGML_RPC=OFF', '-DGGML_VULKAN=OFF', '-DGGML_CURL=OFF',
        '-DGGML_BUILD_TESTS=OFF', '-DGGML_BUILD_EXAMPLES=OFF', '-DLLAMA_BUILD_TESTS=OFF',
        '-DLLAMA_BUILD_EXAMPLES=OFF', '-DLLAMA_BUILD_SERVER=OFF', '-DLLAMA_CURL=OFF',
    ]
    write(out / 'cmake-argv.json', list(map(str, args)))
    elapsed = limited(out, out / 'configure.log', args, 120, GIB // 2)
    obj = out / 'objects'
    ninja = ['/usr/bin/ninja', '-C', obj]
    limited(out, out / 'steps.log', [*ninja, '-n', '-j2', 'llama'], 120, GIB // 2)
    limited(out, out / 'commands.log', [*ninja, '-t', 'commands', 'llama'], 120, GIB // 2)
    commands = (out / 'commands.log').read_text().splitlines()
    cu = [c for c in commands if re.search(r' -c [^ ]+[.]cu(?: |$)', c)]
    require(cu, 'no CUDA commands in actual target')
    for c in cu:
        require(str(cubin) in c and '-ccbin=/usr/bin/g++-15' in c, 'nvcc/host compiler')
        require(re.findall(r'arch=compute_(\d+),code=\[?([^\] ]+)', c) == [('89', 'sm_89')], 'CUDA arch')
        require('--allow-unsupported-compiler' not in c and '-allow-unsupported-compiler' not in c, 'unsupported override')
    links = [c for c in commands if ' -shared ' in c and re.search(r' -o [^ ]*lib(ggml|llama)\.so', c)]
    require(len(links) == 2 and all(any(x in c for c in links) for x in
            ('/libcudart.so', '/libcublas.so', '/libcublasLt.so', '/stubs/libcuda.so')), 'CUDA shared linking')
    require(not list(obj.glob('**/*.cu.o')), 'project CUDA object compiled in configure')
    steps = [s for s in (out / 'steps.log').read_text().splitlines() if re.match(r'^\[\d+/\d+]', s)]
    require(steps and int(steps[-1].split('/')[1].split(']')[0]) == len(steps), 'Ninja step accounting')
    ids = {p: checksum(p) for p in ('/usr/bin/gcc-15', '/usr/bin/g++-15', '/usr/bin/cmake', '/usr/bin/ninja',
                                     str(cubin), str(TOOLKIT / 'include/crt/host_config.h'),
                                     str(TOOLKIT / 'lib64/stubs/libcuda.so'))}
    return {'status': 'PASS_IK_SM89_CONFIGURE_ONLY', 'source': str(src), 'revision': REV, 'tree': TREE,
            'configure_seconds': elapsed, 'ninja_steps': len(steps), 'cuda_translation_units': len(cu),
            'step_kinds': dict(collections.Counter(s.split('] ')[1].split(' object ')[0].split(' library ')[0]
                                                   for s in steps)),
            'provider_provenance': 'sealed ENV49 SHA; full current stat matched, no bulk provider reread',
            'providers': p, 'env49_sha256': ENV49, 'tools_sha256': ids, 'plan_sha256': {f: checksum(obj/f) for f in PLAN_FILES},
            'logs_sha256': {f: checksum(out/f) for f in ('configure.log','steps.log','commands.log','cmake-argv.json')},
            'protocol_sha256': checksum(Path(__file__).with_name('protocol.md')), 'script_sha256': checksum(__file__),
            'output': str(out), 'output_bytes_before_receipt': size(out), 'project_cuda_objects': 0,
            'model_loads': 0, 'gpu_device_nodes_visible': False}


def main():
    a = argparse.ArgumentParser()
    a.add_argument('--source', type=Path, required=True)
    a.add_argument('--env49-map', type=Path, required=True)
    a.add_argument('--new-output-dir', type=Path, required=True)
    args = a.parse_args()
    out = args.new_output_dir.absolute()
    out.mkdir(mode=0o700)
    (out/'tmp').mkdir(mode=0o700)
    try:
        result = configure(args.source.resolve(), out, args.env49_map)
    except Exception as error:
        write(out/'receipt.json', {'status':'FAIL_PRESERVED', 'error':str(error), 'revision':REV})
        raise
    write(out/'receipt.json', result)
    print(result['status'], checksum(out/'receipt.json'))


if __name__ == '__main__':
    main()
