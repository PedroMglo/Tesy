"""Prospective fixed-shape block observer, retaining C211 consumer byte checks."""
import argparse
import hashlib
from pathlib import Path
import tempfile

from c210_prepare_capture import generate


def prepare(output):
    output = Path(output)
    with tempfile.TemporaryDirectory() as directory:
        original = Path(directory) / 'canonical.cpp'
        parent = generate(original)
        source = original.read_text()
    edits = [
        ('    int decode_step = -1;', '    int decode_step = -1;\n    int block_tokens = 1;'),
        ('(chunk == 5 ? 29 : 32)) : 1;', '(chunk == 5 ? 29 : 32)) : state.block_tokens;'),
        ('(state.phase == "prefill0" || state.phase == "decode0");', '(!state.prefill || state.phase == "prefill0");'),
    ]
    for old, new in edits:
        if source.count(old) != 1:
            raise ValueError('observer boundary changed: ' + old)
        source = source.replace(old, new)
    with output.open('x') as handle:
        handle.write(source)
    return dict(parent=parent, generated_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                changes='Declare actual block rows; retain original consumer/generation/bytes checks for all recorded block phases. Historical observer and backend unchanged.')


if __name__ == '__main__':
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    print(json.dumps(prepare(parser.parse_args().output)))
