"""Compile only the original CPU C executor object with a consumer hook for an isolated pilot.
Does not rebuild/replace any shared backend installation or production library.
"""
import hashlib,json,shlex,subprocess
from pathlib import Path
repo=Path(__file__).resolve().parents[1];backend=Path('/tmp/tesy-c75-backend-20260928')
build=repo/'results/c234-readiness-pilot-or-bound-20261001/build';build.mkdir(exist_ok=True)
source=backend/'ggml/src/ggml-cpu/ggml-cpu.c'
text=source.read_text();needle='''        const char * src0_cur = (const char *) src0->data + cur_a * nb02;'''
assert text.count(needle)==1
include='#include "ggml-cpu-impl.h"'
assert include in text
text=text.replace(include,include+'\nextern void tesy_readiness_consume(const struct ggml_tensor *, int, int);',1)
text=text.replace(needle,'        tesy_readiness_consume(src0, cur_a, ith);\n'+needle,1)
generated=build/'ggml-cpu-readiness.c';generated.write_text(text)
records=json.loads((backend/'build-c75-cuda/compile_commands.json').read_text())
record=next(r for r in records if r['file']==str(source));cmd=shlex.split(record['command'])
cmd[cmd.index('-o')+1]=str(build/'ggml-cpu-readiness.o');cmd[cmd.index('-c')+1]=str(generated)
p=subprocess.run(cmd,cwd=record['directory'],capture_output=True,text=True,timeout=90)
(build.parent/'raw/native-hook-build.stdout').write_text(p.stdout);(build.parent/'raw/native-hook-build.stderr').write_text(p.stderr)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
with (build.parent/'native-hook-build.json').open('x') as f:json.dump({'command':cmd,'original_sha256':sha(source),'generated_sha256':sha(generated),'returncode':p.returncode,'change':'One per-used-slot callback before original MMID dot loop; no numerical/chunk/quantization changes','original_toolchain_flags_preserved':True,'shared_runtime_changed':False},f,indent=2);f.write('\n')
if p.returncode:raise SystemExit(p.returncode)
