"""Independent raw BF16/value/metadata audit of the pinned head conversion."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import numpy as np

NAMES = {
    'fc.weight': 'fc.weight',
    'midlayer.hidden_norm.weight': 'blk.0.attn_norm_2.weight',
    'midlayer.input_layernorm.weight': 'blk.0.attn_norm.weight',
    'midlayer.post_attention_layernorm.weight': 'blk.0.ffn_norm.weight',
    'norm.weight': 'output_norm.weight',
    **{'midlayer.mlp.'+x+'_proj.weight': 'blk.0.ffn_'+x+'.weight'
       for x in ('down', 'gate', 'up')},
    **{'midlayer.self_attn.'+x+'_proj.weight': 'blk.0.attn_'+y+'.weight'
       for x, y in [('q','q'), ('k','k'), ('v','v'), ('o','output')]},
}


def rope_rows(shape, heads):
    """Independent row-index oracle: split-half HF RoPE to interleaved GGML."""
    if len(shape) != 2 or shape[0] % (2*heads):
        raise ValueError('invalid RoPE shape/head mapping')
    width = shape[0] // heads
    return np.asarray([h*width + i + half*(width//2) for h in range(heads)
                       for i in range(width//2) for half in (0,1)])


def compare(original, tensor, gguf_type):
    shape = tuple(int(x) for x in reversed(tensor.shape))
    if shape != original.shape:
        raise ValueError('converted tensor shape differs from source')
    if tensor.tensor_type == gguf_type.BF16:
        actual = tensor.data.view('<u2').reshape(shape)
        expected = original
    elif tensor.tensor_type == gguf_type.F32 and original.ndim == 1:
        actual = tensor.data.view('<u4').reshape(shape)
        expected = original.astype('<u4') << 16
    else:
        raise ValueError('unqualified dtype/quantization transformation')
    if not np.array_equal(actual, expected):
        raise ValueError('converted values differ from exact BF16 source/permutation')
    return {'shape': list(shape), 'dtype': tensor.tensor_type.name,
            'elements': original.size, 'exact_source_values': True}


def audit(head, converted, target, backend):
    sys.path.insert(0,str(Path(backend)/'gguf-py'))
    import gguf
    head, converted, target = map(Path, (head,converted,target))
    with (head/'model.safetensors').open('rb') as f:
        size = struct.unpack('<Q',f.read(8))[0]
        if size>32*1024**2: raise ValueError('unbounded safetensors metadata')
        header=json.loads(f.read(size))
    source_names=set(header)-{'__metadata__'}
    if source_names!=set(NAMES):raise ValueError('unqualified/missing head tensors')
    source=np.memmap(head/'model.safetensors',mode='r',dtype=np.uint8)
    out=gguf.GGUFReader(str(converted)); old=gguf.GGUFReader(str(target))
    tensors={t.name:t for t in out.tensors}
    if set(tensors)!=set(NAMES.values())|{'rope_freqs.weight'}:
        raise ValueError('extra/missing converted head tensors')
    if out.fields['general.architecture'].contents()!='eagle3' or \
            out.fields['eagle3.target_layers'].contents()!=[2,18,33]:
        raise ValueError('wrong head architecture/feature indices')
    rows=[]
    for key,name in NAMES.items():
        meta=header[key];a,b=meta['data_offsets'];shape=tuple(meta['shape'])
        if meta['dtype']!='BF16' or a<0 or b-a!=math.prod(shape)*2 or 8+size+b>len(source):
            raise ValueError('invalid source dtype/offset/bytes')
        original=source[8+size+a:8+size+b].view('<u2').reshape(shape)
        if np.any((original & 0x7f80)==0x7f80):raise ValueError('nonfinite source tensor')
        if key.endswith('q_proj.weight'):original=original[rope_rows(shape,64)]
        if key.endswith('k_proj.weight'):original=original[rope_rows(shape,8)]
        try:
            evidence=compare(original,tensors[name],gguf.GGMLQuantizationType)
        except ValueError as exc:
            raise ValueError(key+': '+str(exc)) from exc
        rows.append({'source':key,'converted':name,**evidence})
    # Native converter's deterministic Llama3 frequency factors. Independently
    # apply the three wavelength regions from the pinned head configuration.
    cfg=json.loads((head/'config.json').read_text());scale=cfg['rope_scaling']
    frequencies=[]
    for i in range(cfg['head_dim']//2):
        wavelength=2*math.pi*cfg['rope_theta']**(2*i/cfg['head_dim'])
        if wavelength<scale['original_max_position_embeddings']/scale['high_freq_factor']:
            value=1.0
        elif wavelength>scale['original_max_position_embeddings']/scale['low_freq_factor']:
            value=float(scale['factor'])
        else:
            smooth=(scale['original_max_position_embeddings']/wavelength-scale['low_freq_factor'])/(scale['high_freq_factor']-scale['low_freq_factor'])
            value=1.0/(1.0/scale['factor'] + smooth*(1.0-1.0/scale['factor']))
        frequencies.append(value)
    rope=tensors['rope_freqs.weight']
    expected=np.asarray(frequencies,dtype='<f4')
    actual_rope=rope.data.reshape(-1)
    # The converter derives frequencies with native torch F32 pow/divide before
    # smoothing; this oracle uses FP64 scalar arithmetic. A prospective 2^-18
    # relative bound covers that explicit F32 derivation, not source tensor drift
    # or target logits. Every original source weight still compares exactly.
    if rope.tensor_type!=gguf.GGMLQuantizationType.F32 or actual_rope.shape!=expected.shape or \
            not np.isfinite(actual_rope).all() or not np.all(np.abs(actual_rope-expected)<=expected*2**-18):
        raise ValueError('derived RoPE frequency coefficients differ')
    original_fields={k:v for k,v in old.fields.items() if k.startswith('tokenizer.')}
    copied_fields={k:v for k,v in out.fields.items() if k.startswith('tokenizer.')}
    if set(original_fields)!=set(copied_fields):raise ValueError('tokenizer keys changed')
    for key,field in original_fields.items():
        if field.types!=copied_fields[key].types or field.contents()!=copied_fields[key].contents():
            raise ValueError('tokenizer metadata not identical: '+key)
    return {'status':'PASS_PINNED_HEAD_CONVERSION_VALUES_METADATA',
            'head_sha256':hashlib.sha256((head/'model.safetensors').read_bytes()).hexdigest(),
            'gguf_sha256':hashlib.sha256(converted.read_bytes()).hexdigest(),
            'gguf_bytes':converted.stat().st_size,'tensors':rows,
            'derived_rope_values':len(frequencies),
            'derived_rope_oracle_relative_bound':2**-18,
            'derived_rope_max_relative_error':float(np.max(np.abs(actual_rope-expected)/expected)),
            'original_tokenizer_fields':len(original_fields),
            'target_weights_converted':False,'target_weights_rehashed':False,
            'scope':'Exact head value conversion/metadata only; no head/target forward, fidelity or acceptance qualification'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--head',required=True);p.add_argument('--converted',required=True)
    p.add_argument('--target',required=True);p.add_argument('--backend',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=audit(a.head,a.converted,a.target,a.backend)
    with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(result['status'])


if __name__=='__main__':main()
