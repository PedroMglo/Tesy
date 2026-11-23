"""Pinned native converter adapter: reuse original GGUF tokenizer metadata.

No target weights are converted or fetched. Tensor conversion remains the
original C75 conversion/llama.py implementation, requested BF16 explicitly.
"""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys


def copy_tokenizer(reader, writer, *, expected_vocab=201088):
    fields = {k: v for k, v in reader.fields.items() if k.startswith('tokenizer.')}
    required = {'tokenizer.ggml.model', 'tokenizer.ggml.pre',
                'tokenizer.ggml.tokens', 'tokenizer.ggml.token_type',
                'tokenizer.ggml.merges', 'tokenizer.ggml.eos_token_id',
                'tokenizer.chat_template'}
    if not required <= fields.keys():
        raise ValueError('original tokenizer metadata incomplete')
    if len(fields['tokenizer.ggml.tokens'].data) != expected_vocab or \
            len(fields['tokenizer.ggml.token_type'].data) != expected_vocab:
        raise ValueError('original tokenizer cardinality changed')
    material = {}
    for key, field in sorted(fields.items()):
        value = field.contents()
        writer.add_key_value(key, value, field.types[0],
                             field.types[-1] if len(field.types) == 2 else None)
        material[key] = {'types': [int(t) for t in field.types], 'value': value}
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':')).encode()
    return {'fields': len(material), 'vocab': expected_vocab,
            'canonical_metadata_bytes': len(encoded),
            'sha256_sorted_types_values_v1': hashlib.sha256(encoded).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend', type=Path, required=True)
    parser.add_argument('--head', type=Path, required=True)
    parser.add_argument('--target-gguf', type=Path, required=True)
    parser.add_argument('--outfile', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    if args.outfile.exists() or args.receipt.exists():
        raise ValueError('conversion identity/output already exists')
    backend, head, target = (p.resolve() for p in
                             (args.backend, args.head, args.target_gguf))
    sys.path[:0] = [str(backend), str(backend / 'gguf-py')]
    import gguf
    from conversion.llama import LlamaModel
    reader = gguf.GGUFReader(str(target))
    arch = reader.fields['general.architecture'].contents()
    blocks = reader.fields[arch + '.block_count'].contents()
    hidden = reader.fields[arch + '.embedding_length'].contents()
    if (arch, blocks, hidden) != ('gpt-oss', 36, 2880):
        raise ValueError('original GPT-OSS target metadata changed')
    config = json.loads((head / 'config.json').read_text())
    if config.get('architectures') != ['LlamaForCausalLMEagle3'] or \
            config.get('eagle_config', {}).get('eagle_aux_hidden_state_layer_ids') != [1, 17, 32] or \
            config.get('hidden_size') != hidden or config.get('vocab_size') != 201088:
        raise ValueError('unqualified head feature/tokenizer contract')
    metadata = args.outfile.resolve().parent / (args.outfile.stem + '-target-metadata-from-original-gguf')
    metadata.mkdir(exist_ok=False)
    (metadata / 'config.json').write_text(json.dumps(
        {'num_hidden_layers': blocks, 'hidden_size': hidden, 'vocab_size': 201088}) + '\n')
    receipt = {}

    def original_vocab(self):
        if not getattr(self, 'is_eagle3', False):
            raise ValueError('adapter only admits the specified head')
        receipt['tokenizer'] = copy_tokenizer(reader, self.gguf_writer)

    LlamaModel.set_vocab = original_vocab
    sys.argv = [str(backend / 'convert_hf_to_gguf.py'), str(head),
                '--target-model-dir', str(metadata), '--outtype', 'bf16',
                '--outfile', str(args.outfile.resolve())]
    runpy.run_path(str(backend / 'convert_hf_to_gguf.py'), run_name='__main__')
    receipt.update({'adapter': 'original GGUF tokenizer metadata only',
                    'target_weights_converted': False,
                    'target_features': [2, 18, 33], 'head_dtype_requested': 'BF16',
                    'output': str(args.outfile.resolve()),
                    'output_bytes': args.outfile.stat().st_size})
    if not receipt.get('tokenizer') or args.outfile.stat().st_size > 2 * 1024**3:
        raise ValueError('conversion output or tokenizer evidence invalid')
    with args.receipt.open('x') as f:
        json.dump(receipt, f, indent=2)
        f.write('\n')


if __name__ == '__main__':
    main()
