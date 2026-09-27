"""Offline documentary verification. Does not validate inference or unrestricted prose.
Specs and TeX are trusted, reviewed source code, not a hostile-input sandbox.
"""
from __future__ import annotations
import csv
import ctypes
from datetime import date
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from typing import Any
import jsonschema

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = 'tesy-reporting-1.0.0'
ID = re.compile(r'^[A-Za-z][A-Za-z0-9-]{0,79}$')
SECTIONS = ('01-summary','02-question','03-context','04-contract','05-methodology',
            '06-results','07-failures','08-interpretation','09-limitations',
            '10-decision','11-next-gate','12-appendices')

class EvidenceError(ValueError):
    """Explicit documentary gate failure; missing is never silently zero."""

def require(ok: bool, message: str) -> None:
    if not ok:
        raise EvidenceError(message)

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

def canonical(data: Any) -> bytes:
    return (json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()

def strict_json(data: bytes) -> Any:
    def pairs(items):
        out = {}
        for key,value in items:
            require(key not in out, 'DUPLICATE_JSON_KEY: '+key)
            out[key] = value
        return out
    def constant(value):
        raise EvidenceError('NON_FINITE_JSON: '+value)
    def finite(value):
        if isinstance(value,float):
            require(math.isfinite(value),'NON_FINITE_JSON')
        elif isinstance(value,dict):
            for x in value.values(): finite(x)
        elif isinstance(value,list):
            for x in value: finite(x)
    try:
        out=json.loads(data.decode('utf-8'),object_pairs_hook=pairs,parse_constant=constant)
        finite(out)
        return out
    except (UnicodeError,json.JSONDecodeError) as exc:
        raise EvidenceError('INVALID_JSON: '+str(exc)) from exc

def safe(root: Path, relative: str) -> Path:
    p=PurePosixPath(relative)
    require(bool(relative) and relative!='.' and not p.is_absolute() and str(p)==relative
            and '..' not in p.parts and '\\' not in relative and ':' not in relative,'UNSAFE_PATH: '+relative)
    current=root
    for part in p.parts:
        current=current/part
        require(not current.is_symlink(),'SYMLINK_FORBIDDEN: '+str(current))
    require(current.resolve().is_relative_to(root.resolve()),'PATH_ESCAPE')
    return current

def read(path: Path) -> Any:
    require(path.is_file() and not path.is_symlink(),'MISSING_JSON: '+str(path))
    return strict_json(path.read_bytes())

def validate(root: Path, name: str, data: Any) -> None:
    try:
        jsonschema.Draft202012Validator(read(root/'schema'/(name+'.schema.json'))).validate(data)
    except jsonschema.ValidationError as exc:
        raise EvidenceError('SCHEMA_'+name+': '+str(list(exc.absolute_path))+': '+exc.message) from exc

def unique(rows: list, key: str='id') -> dict:
    out={}
    for row in rows:
        require(row[key] not in out,'DUPLICATE_ID: '+row[key])
        out[row[key]]=row
    return out

def pointer(value: Any, path: str) -> Any:
    require(path=='' or path.startswith('/'),'INVALID_POINTER')
    if path=='': return value
    for token in path[1:].split('/'):
        require(re.search(r'~(?![01])',token) is None,'INVALID_POINTER_ESCAPE')
        token=token.replace('~1','/').replace('~0','~')
        if isinstance(value,dict):
            require(token in value,'MISSING_POINTER: '+path)
            value=value[token]
        elif isinstance(value,list):
            require(re.fullmatch(r'0|[1-9][0-9]*',token) is not None,'INVALID_ARRAY_INDEX')
            require(int(token)<len(value),'MISSING_POINTER: '+path)
            value=value[int(token)]
        else:
            raise EvidenceError('MISSING_POINTER: '+path)
    return value

def folder(root: Path, report_id: str) -> Path:
    require(ID.fullmatch(report_id) is not None,'INVALID_REPORT_ID')
    reg=read(root/'registry.json');validate(root,'registry',reg)
    rows=unique(reg['reports']);require(report_id in rows,'UNREGISTERED_REPORT')
    return safe(root,rows[report_id]['path'])

def source_bytes(root: Path, source: dict, mode: str='snapshot', repo: Path|None=None) -> bytes:
    require(mode in ('snapshot','git'),'UNKNOWN_SOURCE_MODE')
    safe(root,source['path'])
    if mode=='snapshot':
        p=safe(root,'sources/objects/'+source['sha256']+'.source')
        require(p.is_file(),'SOURCE_UNAVAILABLE: '+source['id'])
        data=p.read_bytes()
    else:
        require(repo is not None,'GIT_MODE_REQUIRES_REPO')
        config=subprocess.run(['git','-C',str(repo),'config','--get-regexp',
                               r'^(extensions\.partialclone|remote\..*\.promisor)$'],
                              capture_output=True,timeout=10,check=False)
        require(config.returncode==1,'PARTIAL_OR_UNREADABLE_REPO_FORBIDDEN')
        p=subprocess.run(['git','-c','protocol.allow=never','-C',str(repo),'show',source['commit']+':'+source['path']],
                         capture_output=True,timeout=20,check=False,
                         env={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_TERMINAL_PROMPT':'0'})
        require(p.returncode==0,'GIT_SOURCE_UNAVAILABLE; no network/fallback')
        data=p.stdout
    require(len(data)==source['bytes'],'SOURCE_SIZE_MISMATCH: '+source['id'])
    require(sha(data)==source['sha256'],'SOURCE_SHA256_MISMATCH: '+source['id'])
    require(git_blob(data)==source['git_blob_sha1'],'GIT_BLOB_MISMATCH: '+source['id'])
    return data

def locate(ref: dict, sources: dict) -> Any:
    require(ref['source'] in sources,'UNDECLARED_SOURCE: '+ref['source'])
    data=sources[ref['source']]
    if ref['type']=='json': return pointer(strict_json(data),ref['pointer'])
    require(data.decode().count(ref['quote'])==1,'TEXT_ANCHOR_NOT_UNIQUE: '+ref['source'])
    return ref['quote']

def convert(value, raw: str, unit: str):
    if raw==unit: return value
    divisors={('B','GiB'):2**30,('B','GB'):10**9,('MiB','GiB'):1024,('s','min'):60}
    require((raw,unit) in divisors,'INVALID_UNIT_CONVERSION')
    return value/divisors[(raw,unit)]

def escape(value: Any) -> str:
    chars={'\\':r'\textbackslash{}','&':r'\&','%':r'\%','$':r'\$','#':r'\#',
           '_':r'\_','{':r'\{','}':r'\}','~':r'\textasciitilde{}','^':r'\textasciicircum{}'}
    return ''.join(chars.get(c,c) for c in str(value))

def digest(root: Path, d: Path, spec: dict, cat: dict) -> str:
    files=[d/'campaign.json',d/'evidence-spec.json',d/'report.tex']
    for sub in (d/'sections',root/'template',root/'shared',root/'schema',root/'tools'):
        files += [p for p in sub.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
    entries=[]
    for p in sorted(set(files)):
        rel=p.relative_to(root).as_posix();safe(root,rel)
        entries.append([rel,sha(p.read_bytes())])
    selected=sorted(x['source'] for x in spec['source_contracts'])
    entries.append(['selected-source-catalog',sha(canonical([cat[x] for x in selected]))])
    return sha(canonical(entries))

def verify(root: Path, report_id: str, mode: str='snapshot', repo: Path|None=None) -> dict:
    d=folder(root,report_id);meta=read(d/'campaign.json');spec=read(d/'evidence-spec.json');catalog=read(root/'sources/catalog.json')
    for name,data in [('campaign',meta),('evidence',spec),('sources',catalog)]: validate(root,name,data)
    require(meta['id']==report_id,'REPORT_ID_MISMATCH')
    try: require(date.fromisoformat(meta['date']).isoformat()==meta['date'],'INVALID_REPORT_DATE')
    except ValueError as exc: raise EvidenceError('INVALID_REPORT_DATE') from exc
    for section in SECTIONS: require(safe(d,'sections/'+section+'.tex').is_file(),'MISSING_SECTION: '+section)
    cat=unique(catalog['sources']);keys=[(x['commit'],x['path']) for x in cat.values()]
    require(len(keys)==len(set(keys)),'DUPLICATE_SOURCE_ALIAS')
    contracts=unique(spec['source_contracts'],'source');sources={}
    for sid,contract in contracts.items():
        require(sid in cat,'SOURCE_NOT_IN_CATALOG')
        require(contract['path']==cat[sid]['path'],'AUTHORITY_PATH_MISMATCH')
        require(cat[sid]['commit'] in meta['evidence_snapshot_commits'],'UNPINNED_COMMIT')
        sources[sid]=source_bytes(root,cat[sid],mode,repo)
        for condition in contract['json_values']:
            found=pointer(strict_json(sources[sid]),condition['pointer'])
            require(type(found) is type(condition['expected']) and found==condition['expected'],'AUTHORITY_IDENTITY_MISMATCH')
        for text in contract['text']: require(text in sources[sid].decode(),'AUTHORITY_TEXT_MISSING')
    require(set(sources)=={s for ss in spec['authorities'].values() for s in ss},'AUTHORITY_SOURCE_SET_MISMATCH')
    if meta['state_evidence'] is None:
        require(meta['editorial_state']=='DRAFT','REVIEWED_STATE_REQUIRES_EVIDENCE')
    else:
        state=locate(meta['state_evidence'],sources)
        if meta['state_evidence']['type']=='json': require(state==meta['scientific_state'],'SCIENTIFIC_STATE_MISMATCH')
        else: require(meta['scientific_state'] in state,'SCIENTIFIC_STATE_MISSING')
    definitions=unique(spec['metrics']);claims=unique(spec['claims']);values={};visiting=set()
    def allowed(family,sid):
        require(sid in spec['authorities'].get(family,[]),'SOURCE_NOT_AUTHORITATIVE')
    def metric(mid):
        require(mid in definitions,'UNKNOWN_METRIC: '+mid)
        if mid in values: return values[mid]
        require(mid not in visiting,'METRIC_CYCLE');visiting.add(mid)
        m=definitions[mid];ex=m['extract'];kind=ex['type']
        if kind in ('json','text-number'):
            allowed(m['family'],ex['source']);provenance=[ex['source']]
            if kind=='json': raw=locate(ex,sources)
            else:
                quote=locate({'type':'text','source':ex['source'],'quote':ex['quote']},sources)
                require(len(re.findall(r'(?<![0-9.])'+re.escape(ex['token'])+r'(?![0-9.])',quote))==1,'NUMERIC_TRANSCRIPTION_NOT_UNIQUE')
                raw=float(ex['token']) if '.' in ex['token'] else int(ex['token'])
        else:
            children=[metric(x) for x in ex['inputs']];provenance=sorted({s for x in children for s in x['sources']})
            for sid in provenance: allowed(m['family'],sid)
            if kind=='ratio':
                require(len(children)==2,'RATIO_REQUIRES_TWO_INPUTS');a,b=children
                unit='ratio' if a['unit']==b['unit'] else ('token/s' if (a['unit'],b['unit'])==('token','s') else None)
                require(m['raw_unit']==unit,'RATIO_UNIT_MISMATCH');require(b['value']>0,'INVALID_DENOMINATOR')
                raw=a['value']/b['value']
            else:
                require(all(x['unit']==m['raw_unit'] for x in children),'SUM_UNIT_MISMATCH')
                raw=sum(x['value'] for x in children)
        require(type(raw) in (int,float) and math.isfinite(raw),'NOT_FINITE_NUMERIC: '+mid)
        value=convert(raw,m['raw_unit'],m['unit'])
        values[mid]={**m,'raw':raw,'value':value,'display':f'{value:.{m["decimals"]}f}','sources':provenance}
        visiting.remove(mid);return values[mid]
    for mid in definitions: metric(mid)
    for claim in claims.values():
        for ref in claim['evidence']: allowed(claim['family'],ref['source']);locate(ref,sources)
    for check in spec['checks']:
        if check['type']=='equal':
            a,b=metric(check['left']),metric(check['right']);require(a['unit']==b['unit'],'CROSSCHECK_UNIT_MISMATCH')
            require(abs(a['value']-b['value'])<=check['atol'],'CROSSCHECK_CONFLICT')
        else:
            expected=locate({'type':'json','source':check['source'],'pointer':check['pointer']},sources)
            require(check['target'] in sources and expected==sha(sources[check['target']]),'SOURCE_HASH_LINK_CONFLICT')
    unique(spec['datasets'])
    for ds in spec['datasets']:
        cols=unique(ds['columns'],'key');unique(ds['rows'],'label')
        for row in ds['rows']:
            require(set(row['cells'])==set(cols),'DATASET_COLUMNS_MISMATCH')
            for key,mid in row['cells'].items(): require(metric(mid)['unit']==cols[key]['unit'],'DATASET_UNIT_MISMATCH')
    for p in [d/'report.tex',*sorted((d/'sections').glob('*.tex'))]:
        text=p.read_text()
        for mid in re.findall(r'\\metric\{([^}]+)\}',text): require(mid in values,'UNKNOWN_TEX_METRIC: '+mid)
        for sid in re.findall(r'\\evidence\{([^}]+)\}',text): require(sid in sources,'UNKNOWN_TEX_EVIDENCE: '+sid)
        for cmd,cid in re.findall(r'\\(claim|historicalclaim)\{([^}]+)\}',text):
            require(cid in claims,'UNKNOWN_TEX_CLAIM: '+cid)
            require(cmd=='historicalclaim' or claims[cid]['status']=='CURRENT','NONCURRENT_CLAIM_PROMOTED')
        require(not re.search(r'\\(?:write18|openout|read|catcode)\b',text),'UNSAFE_TEX_PRIMITIVE')
    unique(meta['included_reports'])
    for x in meta['included_reports']:
        require(x['id']!=report_id,'DOSSIER_SELF_REFERENCE');child=folder(root,x['id'])
        require(read(child/'campaign.json')['version']==x['version'],'DOSSIER_VERSION_STALE')
        require(digest(root,child,read(child/'evidence-spec.json'),cat)==x['inputs_sha256'],'DOSSIER_INPUTS_STALE')
    lock={'schema_version':'tesy-lock-v1','adapter':ADAPTER,'inputs_sha256':digest(root,d,spec,cat),'report_id':report_id,'source_mode':mode,
          'sources':[{k:cat[s][k] for k in ('id','commit','path','sha256','git_blob_sha1','bytes')}|{'status':'VERIFIED'} for s in sorted(sources)],
          'checks_passed':len(spec['checks']),'integrity':'PASS','experimental_reproduction':'NOT_RUN','raw_data_availability':'NOT_ACCESSED'}
    validate(root,'lock',lock)
    return {'folder':d,'meta':meta,'spec':spec,'catalog':cat,'sources':sources,'values':values,'claims':claims,'lock':lock}

def generated(v: dict) -> dict[str,bytes]:
    m=v['meta'];out={};lines=['% GENERATED: do not edit.']
    for mid,x in v['values'].items(): lines.append(r'\expandafter\def\csname metric:'+mid+r'\endcsname{\num{'+x['display']+'}}')
    out['metrics.tex']=('\n'.join(lines)+'\n').encode()
    fields={'ReportID':m['id'],'ReportVersion':m['version'],'ReportTitle':m['title'],'ReportSubtitle':m['subtitle'],
            'ReportDate':m['date'],'ReportState':m['scientific_state'],'ReportEditorial':m['editorial_state'],
            'ReportDigest':v['lock']['inputs_sha256'][:12],'ReportScope':m['scope_note'],'ReportLanguage':m['language'],
            'ReportAuthor':m['author'] or '','ReportSourceCount':len(v['sources'])}
    out['metadata.tex']=('\n'.join('\\def\\'+key+'{'+escape(value)+'}' for key,value in fields.items())+'\n').encode()
    lines=[]
    for cid,x in v['claims'].items():
        refs=' '.join(r'\evidence{'+sid+'}' for sid in sorted({e['source'] for e in x['evidence']}))
        lines += [r'\expandafter\def\csname claim:'+cid+r'\endcsname{'+refs+'}',r'\expandafter\def\csname claimstatus:'+cid+r'\endcsname{'+x['status']+'}']
    out['claims.tex']=('\n'.join(lines)+'\n').encode()
    out['values.json']=canonical({'schema_version':'tesy-values-v1','inputs_sha256':v['lock']['inputs_sha256'],'metrics':v['values']})
    lines=[r'\section*{Índice de evidência}',r'Publicações compactas com integridade verificada. Raws: NOT\_ACCESSED; reprodução experimental: NOT\_RUN.']
    for sid in sorted(v['sources']):
        x=v['catalog'][sid];url='https://github.com/PedroMglo/Tesy/blob/'+x['commit']+'/'+x['path']
        lines.append(r'\EvidenceEntry{'+sid+'}{'+x['path']+'}{'+x['commit']+'}{'+x['sha256']+'}{'+url+'}')
    out['evidence-index.tex']=('\n'.join(lines)+'\n').encode()
    for ds in v['spec']['datasets']:
        buf=io.StringIO(newline='');writer=csv.writer(buf,lineterminator='\n');writer.writerow(['label']+[c['key'] for c in ds['columns']])
        for row in ds['rows']: writer.writerow([row['label']]+[repr(v['values'][row['cells'][c['key']]]['value']) for c in ds['columns']])
        out[ds['id']+'.csv']=buf.getvalue().encode()
    out['manifest.json']=canonical({'schema_version':'tesy-derived-manifest-v1','inputs_sha256':v['lock']['inputs_sha256'],'files':{n:sha(b) for n,b in sorted(out.items())}})
    return out

def atomic_write(path: Path, data: bytes) -> None:
    require(not path.is_symlink(),'SYMLINK_FORBIDDEN');path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.write-')
    try:
        with os.fdopen(fd,'wb') as f: f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def derive(v: dict) -> None:
    d=safe(v['folder'],'generated');d.mkdir(exist_ok=True);outputs=generated(v)
    require(not ({p.name for p in d.iterdir()}-set(outputs)),'UNEXPECTED_GENERATED_FILES')
    for n,b in outputs.items(): atomic_write(d/n,b)
    atomic_write(v['folder']/'evidence-lock.json',canonical(v['lock']))

def check_derived(v: dict) -> None:
    d=safe(v['folder'],'generated');outputs=generated(v)
    require(d.is_dir() and {p.name for p in d.iterdir()}==set(outputs),'DERIVED_FILE_SET_MISMATCH')
    for n,b in outputs.items(): require(safe(d,n).read_bytes()==b,'DERIVED_STALE: '+n)
    require(read(v['folder']/'evidence-lock.json')==v['lock'],'EVIDENCE_LOCK_STALE')

def publish_no_replace(staged: Path, destination: Path) -> None:
    """Atomic Linux publication. No racy exists()+rename fallback."""
    require(staged.parent==destination.parent,'PUBLICATION_MUST_BE_SAME_PARENT')
    require(not destination.is_symlink(),'PUBLICATION_SYMLINK_FORBIDDEN')
    libc=ctypes.CDLL(None,use_errno=True);fn=getattr(libc,'renameat2',None)
    require(fn is not None,'ATOMIC_NOREPLACE_UNAVAILABLE')
    fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];fn.restype=ctypes.c_int
    require(fn(-100,os.fsencode(staged),-100,os.fsencode(destination),1)==0,'PUBLICATION_REFUSED: '+str(ctypes.get_errno()))
    fd=os.open(destination.parent,os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)
