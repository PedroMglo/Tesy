"""One rebuilt C75 boundary bridge; reuse immutable C127 references conditionally."""
import argparse
import json
from pathlib import Path

from c210_witness_gate import qualified
from c94_session_wave_8k_reference import tree_digest
from run_bounded import sha256


def analyze(root):
    root=Path(root).resolve();p=json.loads((root/'protocol.json').read_text())
    old=Path(p['reference_capture']);new=root/'raw/c237-rebuild.capture'
    if tree_digest(old)!=p['reference_capture_tree']:
        raise ValueError('immutable canonical reference changed')
    a,b=qualified(old),qualified(new)
    differences={}
    for name in ('core','masks','logits'):
        differences[name]=[str(k) for k in a[name] if a[name][k]!=b[name].get(k)]
        if a[name].keys()!=b[name].keys():raise ValueError('coverage changed')
    passed=not any(differences.values())
    decision=dict(status='PASS_REBUILT_C75_SELECTED_SCOPE' if passed else 'FAIL_REBUILT_IDENTITY_BRIDGE',
                  numeric_states=250,core_payloads=len(b['core']),full_logits=len(b['logits']),
                  prospective_witness=b['prospective_witness'],differences=differences,
                  new_capture_tree=tree_digest(new),reference_capture_tree=p['reference_capture_tree'],
                  reference_chain='Original36FFN references apply only to equal captured payloads, same devices/shapes/arithmetic. New binaries do not inherit historical hashes.',
                  scope='189+32 selected C127 states and five complete logits; not all verifier block rows or full8K',
                  output_ids='Teacher-forced inputs frozen in original numeric fixture; no new generated output ID claim')
    with (root/'numeric-bridge.json').open('x') as f:
        json.dump(decision,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(decision));return 0 if passed else 1


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args()
    raise SystemExit(analyze(a.root))
