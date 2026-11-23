"""Bind start admission to exact serialized policy bytes, not an object digest."""
from pathlib import Path
from run_bounded import sha256
import json
from host_resource_policy import derive_policy,validate_resource_protocol

def bind_start_policy(protocol,path):
 if not Path(path).is_file():raise ValueError('frozen policy file missing')
 r=validate_resource_protocol(protocol)
 policy=json.loads(Path(path).read_text())
 if policy!=derive_policy(snapshot=r['inventory_snapshot']):raise ValueError('collector inventory policy differs from frozen runtime authority')
 protocol['start_inventory']['policy_sha256']=sha256(Path(path))
 return protocol
