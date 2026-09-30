"""Short natural exact-prefix gate; no performance promotion or teacher forcing."""
import json,sys
from pathlib import Path
from c2_server_run import require_natural_completion

def gate(raw_path,ids_path):
 raw=json.loads(Path(raw_path).read_text());rows=raw['results'];expected=json.loads(Path(ids_path).read_text())['ids']
 if raw['stop_reasons'] or raw['returncode']!=0 or len(rows)!=2:raise ValueError('server evidence incomplete')
 tokens=json.loads(Path(str(raw_path).replace('.json','.tokenization.json')).read_text())
 if list(tokens.values())!=[expected,expected]:raise ValueError('official retained prefix IDs changed')
 for index,row in enumerate(rows):
  require_natural_completion(row,256)
  if row['message'].get('content','').strip()!='AB' or row['usage']['prompt_tokens']!=len(expected):raise ValueError('natural function or prompt identity')
  timing=row['timings'];cache=timing['cache_n'];prompt=timing['prompt_n']
  if cache+prompt!=len(expected) or (index==0 and cache!=0) or (index==1 and not max(1,len(expected)-32)<=cache<=len(expected)):raise ValueError('prefix reuse/accounting')
 return {'status':'MMAP_RETAINED_PREFIX_PASS_SHORT_SCOPE','official_ids':len(expected),'common_prefix':len(expected),'cache_n':[r['timings']['cache_n'] for r in rows],'prompt_n':[r['timings']['prompt_n'] for r in rows],'scope':'two identical natural short requests, not153 incremental, session or8192 coverage'}
if __name__=='__main__':print(json.dumps(gate(sys.argv[1],sys.argv[2])))
