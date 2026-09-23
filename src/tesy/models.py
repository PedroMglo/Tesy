"""Explicit model identity and download plans. Never download weights implicitly."""
from __future__ import annotations
import re
from pathlib import Path
from . import gguf
from .io import digest, hash_fd, integer, keys, load_json, require, stable_file, text


def get_model(lock: str | Path, model_id: str) -> dict:
    raw = load_json(lock)
    keys(raw, {'schema', 'models'}, 'model lock')
    require(raw['schema'] == 'tesy.model-lock.v1' and type(raw['models']) is list,
            'model lock schema differs')
    ids, selected = set(), None
    for item in raw['models']:
        keys(item, {'id', 'upstream', 'repository', 'revision', 'file', 'bytes', 'sha256',
                    'architecture', 'quantization', 'license', 'status', 'sources'}, 'model')
        mid = text(item['id'], 'model id')
        require(mid not in ids, 'duplicate model id')
        ids.add(mid)
        require(re.fullmatch(r'[\w.-]+/[\w.-]+', item['repository']) is not None, 'repository differs')
        require(re.fullmatch('[0-9a-f]{40}', item['revision']) is not None, 'immutable revision required')
        file = text(item['file'], 'filename')
        require(Path(file).name == file and file not in ('.', '..') and '\\' not in file
                and not file.startswith('-') and file.endswith('.gguf'), 'unsafe filename')
        integer(item['bytes'], 'model bytes', 1)
        digest(item['sha256'])
        if mid == model_id:
            selected = item
    require(selected is not None, 'unknown model id')
    return selected


def download_plan(model: dict, directory: str | Path) -> dict:
    return {'schema': 'tesy.download-plan.v1', 'classification': 'PLAN_ONLY',
            'downloads_performed': False, 'expected_bytes': model['bytes'],
            'expected_sha256': model['sha256'],
            'argv': ['hf', 'download', model['repository'], model['file'], '--revision',
                     model['revision'], '--local-dir', str(Path(directory).absolute())],
            'note': 'Single monolithic GGUF only. User runs hf after checking free disk.'}


def verify(model: dict, path: str | Path) -> dict:
    with stable_file(path) as (fd, st):
        require(st.st_size == model['bytes'], 'model byte count differs')
        observed = hash_fd(fd, st.st_size)
        require(observed == model['sha256'], 'model SHA-256 differs')
    inv = gguf.inspect(path)
    require(inv['architecture'] == model['architecture'] and inv['is_moe_metadata'],
            'model architecture differs')
    return {'schema': 'tesy.model-verification.v1', 'classification': 'IDENTITY_VERIFIED',
            'model_id': model['id'], 'sha256': observed, 'bytes': model['bytes'],
            'model_loaded': False, 'qualification': False}
