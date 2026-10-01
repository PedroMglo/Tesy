"""Four-request HTTP client for an already running C143; never launches a server."""
import argparse,json,re,time
from pathlib import Path
from c2_gate import GateError,strict_json
from c2_server_run import (stream_chat,_REQUEST_LOCAL,assistant_history_messages,
                          require_natural_completion,validate_generated_prefix_cache)
from run_task_server import fetch
from request_evidence import Deadline,Evidence
import c143_slots40_optin as launcher
from run_bounded import process_identity,sha256


def save(path,data):
    with Path(path).open('x') as f:json.dump(data,f,indent=2,allow_nan=False);f.write('\n');f.flush();__import__('os').fsync(f.fileno())


def native_output_ids(value):
    return (value, 'NATIVE_VERBOSE_FINAL') if type(value) is list and value and all(type(x) is int for x in value) else (None, 'NOT_EXPOSED_EMPTY_OR_ABSENT')

def grade(index,content,first):
    if index==0:return re.fullmatch(r'\d{5}',content) is not None
    if index==1:return content==first
    expected={'projeto':'Lume','local':True,'armazenamento':'disco','porta':18440 if index==2 else 18441}
    try:actual=strict_json(content)
    except (GateError,ValueError):return False
    return type(actual) is dict and actual==expected and type(actual.get('local')) is bool and type(actual.get('porta')) is int


def run(root,protocol_path):
    p=json.loads(protocol_path.read_text());preset=launcher.verified(root)
    endpoint=f'http://127.0.0.1:{preset["port"]}'
    launchpath=root/'raw'/f'{preset["run_id"]}.launch.json'
    ready_timeout=p.get('readiness_after_Popen_s',180)
    if type(ready_timeout) not in (int,float) or not 0<ready_timeout<=180:raise GateError('invalid frozen readiness timeout')
    deadline=time.monotonic()+60+ready_timeout+5
    while not launchpath.exists():
        if (root/'serve-receipt.json').exists():raise GateError('launcher ended before weights launch')
        if time.monotonic()>=deadline:raise GateError('launcher inventory/launch deadline')
        time.sleep(.05)
    launch=json.loads(launchpath.read_text());identity=launch['process_identity'];pid=identity['pid']
    popen=launch['start_inventory']['popen_invoked_monotonic_ns']/1e9
    while True:
        if process_identity(pid)!=identity:raise GateError('launcher model identity changed')
        if time.monotonic()>=popen+ready_timeout:raise GateError('frozen readiness deadline')
        try:
            if fetch('/health',timeout=1,base_url=endpoint).get('status')=='ok':break
        except Exception:pass
        time.sleep(.2)
    ready=time.monotonic();model=fetch('/v1/models',base_url=endpoint)['data'][0]['id']
    history=None;answer=None;first=None;previous_ids=None;previous_outputs=None;rows=[];failure=None
    for index,task in enumerate(p['tasks']):
        evidence=None;wd=None;item=None
        try:
            if process_identity(pid)!=identity or (root/'serve-receipt.json').exists():raise GateError('resource monitor/process ended before request')
            messages=task['messages'] if index==0 else assistant_history_messages(history,answer,task['messages'])
            kwargs={'reasoning_effort':'medium','tesy_template_date':preset['session_date']}
            rendered=fetch('/apply-template',{'model':model,'messages':messages,'chat_template_kwargs':kwargs},base_url=endpoint)
            ids=fetch('/tokenize',{'content':rendered['prompt'],'add_special':False,'parse_special':True},base_url=endpoint)['tokens']
            if not isinstance(ids,list) or any(type(i) is not int for i in ids) or len(ids)>8192-256:raise GateError('official IDs/context reserve invalid')
            save(root/'raw'/f'T{index+1}-input.json',{'messages':messages,'template_kwargs':kwargs,'rendered_prompt':rendered['prompt'],'official_ids':ids})
            start=time.monotonic();evidence=Evidence(root/'raw'/f'T{index+1}-request.jsonl',task['id'],start,task['timeout_s']);_REQUEST_LOCAL.evidence=evidence
            def cancel():launcher.stop(root)
            wd=Deadline(start+task['timeout_s'],cancel);wd.start()
            payload={'model':model,'messages':messages,'chat_template_kwargs':kwargs,'max_tokens':256,'temperature':0,'seed':42,'stream':True,'stream_options':{'include_usage':True},'cache_prompt':True,'return_tokens':True,'verbose':True}
            response,metrics=stream_chat(payload,task['timeout_s'],start,base_url=endpoint)
            end=time.monotonic();valid=wd.complete(end)
            evidence.write('RESPONSE_COMPLETE',response=response,completed_monotonic=end,accepted=False)
            choice=response['choices'][0];item={'id':task['id'],'official_ids':ids,'response':response,'stream_metrics':metrics,'request_started_monotonic':start,'request_ended_monotonic':end,'request_wall_s':end-start,'accepted':False,'deadline_s':task['timeout_s'],'deadline_monotonic':start+task['timeout_s'],'invalid_reason':'VALIDATION_PENDING','finish_reason':choice['finish_reason'],'usage':response['usage'],'timings':response['timings'],'message':choice['message']};rows.append(item)
            save(root/'raw'/f'T{index+1}-complete-unvalidated.json',item)
            if not valid:raise GateError('PER_REQUEST_WALL_TIMEOUT')
            if process_identity(pid)!=identity or (root/'serve-receipt.json').exists():raise GateError('resource monitor/model ended during request')
            require_natural_completion(item,256)
            if item['usage']['prompt_tokens']!=len(ids):raise GateError('official prompt count mismatch')
            t=item['timings'];item['common_prefix']=None
            if index==0:
                if t['cache_n']!=0:raise GateError('first request unexpected cache')
            else:
                common=next((j for j,(a,b) in enumerate(zip(previous_ids,ids)) if a!=b),min(len(previous_ids),len(ids)))
                item['common_prefix']=common
                if index==1:
                    validate_generated_prefix_cache(previous_ids,ids,t['cache_n'],t['prompt_n'],previous_outputs,1900,32)
            item['prefix_gate']='PASS' if index<2 else 'OBSERVED_NOT_PRIMARY_GATE'
            item['content_gate']='PASS' if grade(index,item['message']['content'],first) else 'FAIL_CONTENT'
            if item['content_gate']!='PASS':raise GateError('CONTENT_GATE_FAILED')
            item['accepted']=True;item['invalid_reason']=None
            evidence.write('REQUEST_TERMINAL',accepted=True,watchdog=wd.finish());evidence.close();_REQUEST_LOCAL.evidence=None
            # Actual output IDs, if native verbose SSE exposes them. No retokenization equivalence claim.
            verbose=[]
            for row in map(json.loads,(root/'raw'/f'T{index+1}-request.jsonl').read_text().splitlines()):
                if row['kind']=='SSE_FRAGMENT' and row['fragment'].startswith('data: ') and '[DONE]' not in row['fragment']:
                    obj=json.loads(row['fragment'][6:]);v=obj.get('__verbose')
                    if v is not None:verbose.append(v)
            native_ids=verbose[-1].get('tokens') if verbose else None
            item['output_ids'],item['output_ids_authority']=native_output_ids(native_ids)
            # C188 preserved old raw with tokens=[]; no token IDs can be inferred from that array.
            save(root/'raw'/f'T{index+1}-result.json',item)
            history,answer=messages,item['message'];previous_ids=ids;previous_outputs=item['usage']['completion_tokens']
            if index==0:first=item['message']['content']
        except Exception as exc:
            failure=f'{type(exc).__name__}:{exc}'
            if item is not None:item['accepted']=False;item['invalid_reason']=failure
            if evidence is not None:
                if not evidence.truncated:evidence.write('REQUEST_TERMINAL',accepted=False,invalid_reason=failure,transport_complete=item is not None,watchdog=wd.finish() if wd else None)
                evidence.close()
            _REQUEST_LOCAL.evidence=None
            break # never launch a later request after failure
    result={'status':'CLIENT_FOUR_REQUESTS_PASS' if failure is None and len(rows)==4 else 'CLIENT_FAILED_PRESERVED','failure':failure,'rows':rows,'launch_sha256':sha256(launchpath),'process_identity':identity,'ready_monotonic':ready,'readiness_after_popen_s':ready-popen,'endpoint':endpoint,'preset_sha256':sha256(root/'preset.json'),'scope':'integration descriptive only; no A/B/M4/quality suite'}
    save(root/'client-receipt.json',result);return result

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('root',type=Path);ap.add_argument('protocol',type=Path);a=ap.parse_args();r=run(a.root,a.protocol);print(r['status'],r['failure']);raise SystemExit(0 if r['failure'] is None else 1)
