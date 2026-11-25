"""Repeat the exact derivation under a hard pre-exec address-space ceiling."""

import argparse
import hashlib
import json
import os
import resource
import runpy
import signal
import subprocess
import sys
from pathlib import Path

CAP = 512 * 2**20
PROGRAM = "faf815b1a6dfdbb4a1c7aab273d857b26269da1d64dd80b0644b353238b1a201"
PASS = "PASS_DERIVED_C290_NVME_METADATA"


def check(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, payload):
    with path.open("x") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")


def memory():
    result = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        key = line.partition(":")[0]
        if key in ("VmHWM", "VmPeak", "VmSize", "VmRSS"):
            _, value, unit = line.split()
            check(unit == "kB", "unexpected proc unit")
            result[key + "_kib"] = int(value)
    check(len(result) == 4, "incomplete process-memory witness")
    result["ru_maxrss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result["rlimit_as_bytes"] = list(resource.getrlimit(resource.RLIMIT_AS))
    return result


def check_image(snapshot):
    check(snapshot["rlimit_as_bytes"] == [CAP, CAP], "AS ceiling missing at Python entry/exit")
    check(
        0 < snapshot["VmHWM_kib"] <= snapshot["VmPeak_kib"] <= CAP // 1024,
        "own address-space/RSS high-water at entry/exit",
    )


def child(evidence, program, args):
    observations = {"pid": os.getpid(), "ppid": os.getppid(), "entry": memory()}
    try:
        check_image(observations["entry"])
        check(
            Path("/proc", str(os.getppid()), "exe").samefile("/usr/bin/time"),
            "independent GNU time parent",
        )
        check(sha(program) == PROGRAM, "changed derivation")
        sys.argv = [str(program), *args]
        try:
            runpy.run_path(str(program), run_name="__main__")
            return 0
        except SystemExit as exc:
            return int(exc.code or 0)
    finally:
        observations["exit"] = memory()
        write(evidence, observations)
        check_image(observations["exit"])


def supervise(proof_dir, program, args):
    os.umask(0o077)
    proof_dir = proof_dir.absolute()
    proof_dir.mkdir(mode=0o700)
    result = {"status": "FAIL_PRESERVED", "limit_bytes": CAP, "program_sha256": PROGRAM}
    try:
        check(program.name == "derive.py" and sha(program) == PROGRAM, "original frozen program")
        check(args.count("--new-output-dir") == 1, "one fresh derived destination")
        dest = Path(args[args.index("--new-output-dir") + 1]).absolute()
        check(not os.path.lexists(dest), "derived destination exists")
        evidence = proof_dir / "image.json"
        timing = proof_dir / "time.txt"
        env = dict(os.environ, LC_ALL="C", PYTHONCOERCECLOCALE="0", PYTHONUTF8="1")
        check(
            not any(env.get(k) for k in ("LD_PRELOAD", "LD_AUDIT", "LD_LIBRARY_PATH")),
            "unexpected loader override",
        )
        binary = Path(sys.executable).resolve()
        result["tools_sha256"] = {
            p.name: sha(p)
            for p in (binary, Path("/usr/bin/prlimit"), Path("/usr/bin/time"), Path(__file__))
        }
        argv = [
            "/usr/bin/prlimit",
            f"--as={CAP}:{CAP}",
            "--",
            "/usr/bin/time",
            "-f",
            "%M %e %x",
            "-o",
            timing,
            binary,
            "-IB",
            Path(__file__).resolve(),
            "--child",
            evidence,
            program,
            *args,
        ]
        with (proof_dir / "stdout").open("x") as out, (proof_dir / "stderr").open("x") as err:
            with subprocess.Popen(
                argv, env=env, stdout=out, stderr=err, start_new_session=True
            ) as proc:
                try:
                    code = proc.wait(timeout=120)
                finally:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
        result["child_returncode"] = code
        check(code == 0, "derived child failed")
        maxrss, seconds, exitcode = timing.read_text().strip().split()
        observations = json.loads(evidence.read_text())
        for bound in ("entry", "exit"):
            check_image(observations[bound])
        r = dest / "receipt.json"
        parsed = json.loads(r.read_text())
        check(
            int(exitcode) == 0 and 0 < int(maxrss) <= CAP // 1024 and 0 <= float(seconds) <= 120,
            "GNU time accounting",
        )
        check(
            parsed["status"] == PASS
            and parsed["program_sha256"] == PROGRAM
            and parsed["payload_read_bytes"] == 0,
            "internal derivation result",
        )
        result.update(
            status="PASS_DERIVATION_IN_PREEXEC_AS_LIMIT",
            image=observations,
            time_maxrss_kib=int(maxrss),
            elapsed_s=float(seconds),
            derived_sha256=sha(r),
        )
    except Exception as exc:
        result.update(reason=f"{type(exc).__name__}: {exc}")
    write(proof_dir / "receipt.json", result)
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--child"]:
        raise SystemExit(child(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4:]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usage-dir", type=Path, required=True)
    parser.add_argument("program", type=Path)
    parser.add_argument("args", nargs=argparse.REMAINDER)
    a = parser.parse_args()
    raise SystemExit(supervise(a.usage_dir, a.program.resolve(strict=True), a.args))
