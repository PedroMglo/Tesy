"""Bind start admission to exact serialized policy bytes, not an object digest."""
from pathlib import Path
from run_bounded import sha256

def bind_start_policy(protocol,path):
 if not Path(path).is_file():raise ValueError('frozen policy file missing')
 protocol['start_inventory']['policy_sha256']=sha256(Path(path))
 return protocol
