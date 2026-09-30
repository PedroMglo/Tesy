from pathlib import Path
import json,sys
from residency_capture_gate import capture

def analyze(path):
 p=json.loads(path.read_text());out=[]
 for run in p['runs']:
  e=run['env'];r=capture(Path(run['command'][-1]),Path(e['TESY_C84_EXPERT_TRACE_FILE']),Path(e['TESY_C152_ROUTE_FILE']),[e['TESY_C152_'+x+'_HASH'] for x in ('MODEL','SOURCE','BUILD','PROFILE')]);out.append({'id':run['id'],**r})
 with (path.parent/'capture-summary.json').open('x') as f:json.dump({'captures':out,'status':'FROZEN_HOLDOUT_LOGICAL_CAPTURES_VALIDATED','numeric_bridge':'C159 short original bridge and C161/C162 warm OFF/ON; heldouts finite/logit complete, no paired correctness equivalence across conversations'},f,indent=2)
 print(json.dumps(out))
if __name__=='__main__':analyze(Path(sys.argv[1]))
