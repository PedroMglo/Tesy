"""Small honest CLI: implemented commands only; no fake optimized chat mode."""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from . import __version__, baseline, doctor, gguf, models, planner, residency
from .io import ContractError, canonical, load_json, publish, read_bytes


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='tesy')
    p.add_argument('--version', action='version', version=__version__)
    sub = p.add_subparsers(dest='cmd', required=True)
    d = sub.add_parser('doctor', help='read-only observation of this host')
    d.add_argument('--output', type=Path)
    m = sub.add_parser('models')
    ms = m.add_subparsers(dest='model_cmd', required=True)
    i = ms.add_parser('inspect', help='metadata-only bounded GGUF v3 inventory')
    i.add_argument('path', type=Path)
    i.add_argument('--output', type=Path)
    for name in ('verify', 'download-plan'):
        obj = ms.add_parser(name)
        obj.add_argument('--lock', type=Path, default=Path('configs/models.lock.json'))
        obj.add_argument('--id', required=True)
        obj.add_argument('path', type=Path)
        obj.add_argument('--output', type=Path)
    r = sub.add_parser('simulate', help='serial two-tier replay, not measured speedup')
    r.add_argument('--trace', required=True, type=Path)
    r.add_argument('--profile', required=True, type=Path)
    r.add_argument('--policy', choices=('lru', 'lfu', 'transition'), default='lru')
    r.add_argument('--output', type=Path)
    u = sub.add_parser('union', help='offline target-route union; not acceptance')
    u.add_argument('--trace', required=True, type=Path)
    u.add_argument('--k', required=True, type=int)
    u.add_argument('--output', type=Path)
    r = sub.add_parser('plan', help='per-tier transport bound from explicit inputs')
    r.add_argument('--contract', required=True, type=Path)
    r.add_argument('--output', type=Path)
    c = sub.add_parser('chat', help='explicit STOCK baseline handoff; not dynamic caching')
    c.add_argument('--model', type=Path, required=True)
    c.add_argument('--id', default='qwen3-30b-a3b-2507-q4km')
    c.add_argument('--lock', type=Path, default=Path('configs/models.lock.json'))
    c.add_argument('--backend-lock', type=Path, default=Path('configs/backend.lock.json'))
    c.add_argument('--llama-cli', type=Path, required=True)
    c.add_argument('--cpu-only', action='store_true')
    c.add_argument('--execute', action='store_true', help='otherwise only print planned command')
    c.add_argument('--seconds', type=int, default=600)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.cmd == 'doctor':
            result = doctor.snapshot()
        elif args.cmd == 'models':
            if args.model_cmd == 'inspect':
                result = gguf.inspect(args.path)
            else:
                model = models.get_model(args.lock, args.id)
                result = (models.verify(model, args.path) if args.model_cmd == 'verify'
                          else models.download_plan(model, args.path))
        elif args.cmd in ('simulate', 'union'):
            raw = read_bytes(args.trace)
            # Single read identity for both parsing and published input digest.
            from .io import parse_json
            trace = residency.parse_trace(parse_json(raw))
            if args.cmd == 'simulate':
                prof_raw = read_bytes(args.profile)
                result = residency.replay(trace, parse_json(prof_raw), args.policy)
                result['profile_sha256'] = hashlib.sha256(prof_raw).hexdigest()
            else:
                result = residency.union_windows(trace, args.k)
            result['trace_sha256'] = hashlib.sha256(raw).hexdigest()
        elif args.cmd == 'plan':
            raw = read_bytes(args.contract)
            from .io import parse_json
            result = planner.transport_bound(parse_json(raw))
            result['contract_sha256'] = hashlib.sha256(raw).hexdigest()
        else:
            model = models.get_model(args.lock, args.id)
            if args.execute:
                return baseline.execute(model, args.model, args.llama_cli,
                                        args.backend_lock, args.cpu_only, args.seconds)
            result = {'classification': 'STOCK_BASELINE_PLAN_ONLY', 'model_loaded': False,
                      'optimized_tesy': False, 'qualification': False,
                      'argv': baseline.command(args.llama_cli.absolute(),
                                               str(args.model.absolute()), args.cpu_only),
                      'warning': 'Requires locked build, model verification and live resource checks.'}
        out = getattr(args, 'output', None)
        if out:
            sha = publish(out, result)
            print(json.dumps({'output': str(out), 'sha256': sha}))
        else:
            sys.stdout.buffer.write(canonical(result))
        return 0
    except (ContractError, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'TESY_ERROR: {exc}', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('TESY_CANCELLED: no retry', file=sys.stderr)
        return 130
