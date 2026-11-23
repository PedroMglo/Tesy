import math
import os
import struct

import pytest

from tesy.gguf import inspect
from tesy.io import ContractError


def string(s):
    b = s.encode()
    return struct.pack('<Q', len(b)) + b


def fixture(tmp_path, *, metadata=None, tensors=None, version=3):
    if metadata is None:
        metadata = [('general.architecture',8,'qwen3moe'),
                    ('qwen3moe.expert_count',4,3), ('qwen3moe.expert_used_count',4,1)]
    if tensors is None:
        tensors = [('blk.0.ffn_gate_exps.weight',[2,2,3],0,0)]
    out = b'GGUF' + struct.pack('<IQQ',version,len(tensors),len(metadata))
    for key, kind, value in metadata:
        out += string(key)+struct.pack('<I',kind)
        if kind==8:
            out += string(value)
        elif kind==9:
            out += struct.pack('<IQ',8,len(value))+b''.join(string(v) for v in value)
        elif kind==7:
            out += struct.pack('<B',value)
        elif kind==6:
            out += struct.pack('<f',value)
        else:
            out += struct.pack('<I',value)
    for name,shape,kind,offset in tensors:
        out += string(name)+struct.pack('<I',len(shape))
        out += b''.join(struct.pack('<Q',d) for d in shape)+struct.pack('<IQ',kind,offset)
    out += bytes((-len(out))%32)
    data_start=len(out)
    out += bytes(512)
    p=tmp_path/'tiny.gguf'
    p.write_bytes(out)
    return p, data_start


def test_inspect_metadata_without_weight_read(tmp_path, monkeypatch):
    p,start=fixture(tmp_path)
    pread=os.pread
    def guard(fd,n,offset):
        assert offset+n<=start
        return pread(fd,n,offset)
    monkeypatch.setattr(os,'pread',guard)
    value=inspect(p)
    assert value['architecture']=='qwen3moe' and value['expert_count']==3
    assert value['encoded_tensor_bytes']==48 and value['tensor_count']==1
    assert value['weights_read'] is False and value['qualification'] is False


def test_tokenizer_array_consumed_not_retained(tmp_path):
    p,_=fixture(tmp_path,metadata=[('general.architecture',8,'qwen3moe'),
                                 ('tokenizer.ggml.tokens',9,['a','b','c'])])
    assert 'tokenizer.ggml.tokens' not in inspect(p)['metadata']


@pytest.mark.parametrize('metadata',[
    [('general.architecture',8,'x'),('general.architecture',8,'y')],
    [('general.architecture',8,'x'),('general.alignment',4,3)],
    [('general.architecture',8,'x'),('split.count',4,2)],
    [('general.architecture',8,'x'),('bad',7,2)],
    [('general.architecture',8,'x'),('bad',6,float('nan'))],
    [('general.architecture',8,'x'),('x.expert_count',4,3),('x.expert_used_count',4,4)],
    [('general.architecture',4,5)],
    [('bad key',8,'x')],
])
def test_bad_metadata(tmp_path,metadata):
    p,_=fixture(tmp_path,metadata=metadata)
    with pytest.raises(ContractError):
        inspect(p)


@pytest.mark.parametrize('tensors',[
    [('a',[2,2],99,0)],
    [('a',[2,2],0,1)],
    [('a',[2,2],0,0),('a',[2,2],0,32)],
    [('a',[16,16],0,0)],
    [('a',[4,4],0,0),('b',[4,4],0,32)],
    [('a',[2,2],12,0)],
    [('a',[0,2],0,0)],
    [('a',[2,2],0,1000000)],
])
def test_bad_tensor_geometry(tmp_path,tensors):
    p,_=fixture(tmp_path,tensors=tensors)
    with pytest.raises(ContractError):
        inspect(p)


@pytest.mark.parametrize('version',[0,1,2,4,0x03000000])
def test_version_explicit(tmp_path,version):
    p,_=fixture(tmp_path,version=version)
    with pytest.raises(ContractError):
        inspect(p)


def test_truncation_and_budget(tmp_path):
    p,_=fixture(tmp_path)
    with pytest.raises(ContractError):
        inspect(p,24)
    p.write_bytes(b'GGUF'+struct.pack('<I',3))
    with pytest.raises(ContractError):
        inspect(p)


def test_all_header_truncations_fail_closed(tmp_path):
    p,start=fixture(tmp_path)
    raw=p.read_bytes()
    for size in range(start):
        p.write_bytes(raw[:size])
        with pytest.raises(ContractError): inspect(p)
