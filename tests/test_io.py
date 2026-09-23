import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tesy.io import (ContractError, canonical, integer, parse_json, publish,
                     read_bytes, stable_file)


@pytest.mark.parametrize('raw', [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}',
                                 b'{"x":1e999}', b'{} garbage', b'\xff', b'['*1000+b']'*1000])
def test_reject_bad_json(raw):
    with pytest.raises(ContractError):
        parse_json(raw)


@pytest.mark.parametrize('v', [True, False, 1.0, '1', -1, None, 2**64])
def test_integer_not_alias(v):
    with pytest.raises(ContractError):
        integer(v, 'value')


def test_byte_budget():
    with pytest.raises(ContractError):
        parse_json(b'{}', 1)


def test_publish_no_replace_readback(tmp_path):
    p = tmp_path/'out.json'
    sha = publish(p, {'hello':'olá'})
    assert len(sha) == 64 and read_bytes(p) == canonical({'hello':'olá'})
    with pytest.raises(FileExistsError):
        publish(p, {'oops':1})
    assert not list(tmp_path.glob('.tesy-*'))
    assert b'hello' in p.read_bytes()


def test_publish_race_has_single_winner(tmp_path):
    p = tmp_path/'out.json'
    def attempt(i):
        try:
            publish(p, {'writer':i})
            return True
        except FileExistsError:
            return False
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert sum(pool.map(attempt, range(12))) == 1
    assert 'writer' in parse_json(p.read_bytes())


def test_reject_symlink_input_output_and_parent(tmp_path):
    p = tmp_path/'real'
    p.write_text('data')
    alias = tmp_path/'alias'
    alias.symlink_to(p)
    with pytest.raises(ContractError):
        read_bytes(alias)
    with pytest.raises(FileExistsError):
        publish(alias, {})
    dangling = tmp_path/'dangling'
    dangling.symlink_to(tmp_path/'missing')
    with pytest.raises(FileExistsError):
        publish(dangling, {})
    parent = tmp_path/'parent'
    parent.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ContractError):
        publish(parent/'x', {})


def test_same_fd_detects_replacement(tmp_path):
    p = tmp_path/'file'
    p.write_bytes(b'original')
    with pytest.raises(ContractError):
        with stable_file(p) as (fd, _):
            q = tmp_path/'next'
            q.write_bytes(b'replaced')
            q.replace(p)
            assert os.read(fd, 8) == b'original'


def test_stable_file_detects_mutation(tmp_path):
    p = tmp_path/'file'
    p.write_bytes(b'a')
    with pytest.raises(ContractError):
        with stable_file(p):
            p.write_bytes(b'changed')


def test_regular_file_and_budget(tmp_path):
    p = tmp_path/'file'
    p.write_bytes(b'123')
    with pytest.raises(ContractError):
        read_bytes(p,2)
    with pytest.raises(ContractError):
        read_bytes(tmp_path)


def test_final_file_retained_on_readback_failure(tmp_path, monkeypatch):
    import tesy.io as io
    monkeypatch.setattr(io, 'read_bytes', lambda _: b'wrong')
    p = tmp_path/'out.json'
    with pytest.raises(ContractError):
        publish(p, {'record':'retained'})
    assert p.exists() and not list(tmp_path.glob('.tesy-*'))


def test_oversized_publication_rejected_before_any_write(tmp_path, monkeypatch):
    import tesy.io as io
    monkeypatch.setattr(io, 'canonical', lambda _: b'x' * ((32 << 20) + 1))
    with pytest.raises(ContractError, match='readback byte budget'):
        publish(tmp_path/'too-large.json', {})
    assert list(tmp_path.iterdir()) == []
