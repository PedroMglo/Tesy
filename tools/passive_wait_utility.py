"""Prospective task outcome and penalized utility; historical accept/gates remain separate."""
import json,math,re,time
from statistics import median
from c2_gate import GateError
from native64_sql import grade

JSON_ID='passive-json-pipeline'
JSON_DATA=[{'id':'b','versao':2,'ingest':8,'cancelado':False,'valor':7},{'id':'a','versao':3,'ingest':4,'cancelado':False,'valor':None},{'id':'b','versao':1,'ingest':10,'cancelado':False,'valor':99},{'id':'c','versao':2,'ingest':5,'cancelado':True,'valor':20},{'id':'a','versao':3,'ingest':6,'cancelado':False,'valor':4},{'id':'d','versao':1,'ingest':2,'cancelado':False},{'id':'b','versao':2,'ingest':8,'cancelado':False,'valor':7},{'id':'c','versao':1,'ingest':3,'cancelado':False,'valor':6}]
JSON_PROMPT='''Processa localmente os registos JSON abaixo como um pequeno pipeline. Por id, escolhe o registo de maior versao; em empate escolhe o maior ingest. Duplicados com o mesmo (id,versao,ingest) sao identicos e contam uma unica vez. Depois da selecao, remove os registos cancelado=true; nao recuperes uma versao antiga. Valor inteiro ausente ou null vale 0; unidades sao inteiras. Ordena por id em ordem ASCII crescente. Responde apenas um objeto JSON com chaves itens e total. itens e uma lista de objetos com exatamente id e valor; total soma os valores selecionados. Nao inclua prose ou bloco Markdown. Dados:\n'''+json.dumps(JSON_DATA,separators=(',',':'))

def oracle(records):
 chosen={}
 for r in records:
  key=(r['versao'],r['ingest'])
  if r['id'] not in chosen or key>(chosen[r['id']]['versao'],chosen[r['id']]['ingest']):chosen[r['id']]=r
 items=[{'id':k,'valor':r.get('valor') or 0} for k,r in sorted(chosen.items()) if not r['cancelado']]
 return {'itens':items,'total':sum(r['valor'] for r in items)}
JSON_EXPECTED=oracle(JSON_DATA)

def strict_object(text):
 def pairs(rows):
  out={}
  for k,v in rows:
   if k in out:raise ValueError('duplicate JSON key')
   out[k]=v
  return out
 return json.loads(text,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON')))

def grade_json(text):
 obj=strict_object(text)
 if type(obj)!=dict or set(obj)!=set(JSON_EXPECTED) or type(obj.get('total')) is not int or type(obj.get('itens')) is not list:raise GateError('JSON schema invalid')
 if any(type(r)!=dict or set(r)!= {'id','valor'} or type(r['id']) is not str or type(r['valor']) is not int for r in obj['itens']):raise GateError('JSON item invalid')
 if obj!=JSON_EXPECTED:raise GateError('JSON pipeline result wrong')
 return {'PASS':True,'scope':'fixed version/duplicate/cancellation/null data transform'}

def checker():
 def check(rid,item):
  start=time.monotonic();text=item.get('message',{}).get('content')
  try:
   if item.get('finish_reason')=='length':return {'PASS':False,'outcome':'OUTPUT_CAP','validated_monotonic_s':time.monotonic(),'validator_duration_s':0}
   if type(text) is not str or not text.strip():raise GateError('no final content')
   if rid=='c112-code':result={'PASS':bool(re.fullmatch('[0-9]{5}',text.strip()))}
   elif rid=='c112-repeat':result={'PASS':text.strip()=='48327'}
   elif rid==JSON_ID:result=grade_json(text.strip())
   else:result=grade(text.strip())
  except (GateError,ValueError) as exc:result={'PASS':False,'reason':str(exc)}
  result.update(outcome='SUCCESS' if result['PASS'] else 'WRONG_FINAL',validated_monotonic_s=time.monotonic(),validator_duration_s=time.monotonic()-start)
  return result
 return check

def task_loss(item,deadline,*,valid=True):
 if not valid:return None
 if type(deadline) not in (int,float) or not math.isfinite(deadline) or deadline<=0:raise GateError('deadline invalid')
 if item.get('outcome') in ('OUTPUT_CAP','WRONG_FINAL','DEADLINE_CENSORED'):return 1.0
 if item.get('outcome')!='SUCCESS' or not item.get('functional_success'):raise GateError('outcome unclassified')
 t=item.get('validated_s');v=item.get('validator_s');r=item.get('completion_s')
 if any(type(x) not in (int,float) or not math.isfinite(x) or x<=0 for x in (t,r)) or type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=2:raise GateError('utility timestamp/validator invalid')
 return t/(deadline+2) if r<deadline and t<=deadline+2 else 1.0

PROTECTED=('T2_first_final_s','T2_completion_s','SQL_first_final_s','cold_prefill_s','cold_first_final_s','incremental_prefill_s','T2_seconds_per_output','SQL_seconds_per_output')
def evaluate(pairs,confirmation=False):
 required=3 if confirmation else 2
 if len(pairs)!=required:return {'status':'INCONCLUSIVE_INCOMPLETE_PAIRS'}
 gains={'SQL_L':[]};protected={k:[] for k in PROTECTED};functional=[]
 if confirmation:gains.update(JSON_L=[],U=[]);protected.update(JSON_first_final_s=[],JSON_seconds_per_output=[])
 for a,b in pairs:
  if not a['measurement_valid'] or not b['measurement_valid']:return {'status':'INCONCLUSIVE_MEASUREMENT_INVALID'}
  if a['input_ids']!=b['input_ids'] or not a['nominal153'] or not b['nominal153']:return {'status':'INCONCLUSIVE_INPUT_OR_PREFIX'}
  for ar,br in zip(a['requests'],b['requests']):
   if ar['outcome']=='DEADLINE_CENSORED' or br['outcome']=='DEADLINE_CENSORED':
    # Exact partial compatibility is separately recorded by analyzer; absent proof invalidates.
    def message(r):
     return r['trajectory'] if r['outcome']=='DEADLINE_CENSORED' else r['trajectory']['message']
    am,bm=message(ar),message(br)
    for key in ('content','reasoning_content'):
     x,y=am.get(key) or '',bm.get(key) or ''
     if not (x.startswith(y) or y.startswith(x)):return {'status':'FAIL_SAME_PROFILE_OBSERVED_PREFIX'}
   elif ar['trajectory']!=br['trajectory']:return {'status':'FAIL_SAME_PROFILE_OBSERVABLE_TRAJECTORY'}
   functional.append(br['functional_success']>=ar['functional_success'])
  if not all(r['functional_success'] for r in a['requests'][:2]+b['requests'][:2]):return {'status':'NO_GO_ANCHOR_FUNCTIONAL'}
  for k in gains:
   av,bv=a[k],b[k]
   if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (av,bv)):return {'status':'INCONCLUSIVE_INVALID_UTILITY'}
   gains[k].append(100*(av-bv)/av)
  for k in protected:
   av,bv=a.get(k),b.get(k)
   if av is None or bv is None:
    idx=3 if k.startswith('JSON') else (2 if k.startswith('SQL') else 1)
    if not any(r['outcome'] in ('OUTPUT_CAP','WRONG_FINAL','DEADLINE_CENSORED') for r in (a['requests'][idx],b['requests'][idx])):return {'status':'INCONCLUSIVE_MISSING_PROTECTION','metric':k}
    protected[k].append(None);continue
   if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (av,bv)):return {'status':'INCONCLUSIVE_INVALID_PROTECTION','metric':k}
   protected[k].append(100*(av-bv)/av)
 thresholds={'SQL_L':8,**({'JSON_L':5,'U':5} if confirmation else {})}
 primary=all(median(vals)>=thresholds[k] and all(v>0 for v in vals) for k,vals in gains.items())
 protections=all((not [v for v in vals if v is not None]) or (median([v for v in vals if v is not None])>=-5 and all(v>=-15 for v in vals if v is not None)) for vals in protected.values())
 return {'status':('GO_C_CONFIRMATION' if confirmation else 'GO_S_SCREEN') if primary and protections and all(functional) else ('NO_GO_USEFUL_CONFIRMATION' if confirmation else 'NO_GO_USEFUL_LATENCY_SCREEN'),
 'paired_gains':gains,'medians':{k:median(v) for k,v in gains.items()},'protected_gains':protected,'protected_medians':{k:median([v for v in vals if v is not None]) if any(v is not None for v in vals) else 'NOT_COMPUTABLE_FUNCTIONAL_CENSURE' for k,vals in protected.items()},'functional_noninferiority':functional,'missing_not_zero':True,'scope':'penalized utility, not latency of failed tasks'}

def terminal_censor_contract(raw,evidence,expected_id):
 """Only a witnessed watchdog cancellation of the final task, never arbitrary exceptions."""
 reasons=raw.get('stop_reasons',[])
 if 'PER_REQUEST_WALL_TIMEOUT' not in reasons or any(not (r=='PER_REQUEST_WALL_TIMEOUT' or r.startswith('RUN_ERROR:')) for r in reasons):raise GateError('not isolated request deadline')
 if raw.get('returncode') not in (0,-15):raise GateError('unexpected cancellation exit')
 if any(r.get('kind')=='EVIDENCE_TRUNCATED' or r.get('request_id')!=expected_id for r in evidence):raise GateError('censor evidence missing/truncated/crossed')
 starts=[r for r in evidence if r.get('kind')=='REQUEST_START'];terms=[r for r in evidence if r.get('kind')=='REQUEST_TERMINAL']
 if len(starts)!=1 or len(terms)!=1:raise GateError('censor terminal identity missing')
 watchdog=terms[0].get('watchdog') or {};expiry=watchdog.get('expired_monotonic');cancel=watchdog.get('cancel_requested_monotonic');finished=watchdog.get('cancel_finished_monotonic');deadline=starts[0]['deadline_monotonic']
 if any(type(x) not in (int,float) or not math.isfinite(x) for x in (deadline,expiry,cancel,finished)) or not deadline<=expiry<=cancel<=finished or watchdog.get('cancel_error'):raise GateError('censor watchdog/cancel failed')
 return {'outcome':'DEADLINE_CENSORED','deadline_monotonic':deadline,'expiry_monotonic':expiry,'cancel_requested_monotonic':cancel,'cancel_finished_monotonic':finished}
