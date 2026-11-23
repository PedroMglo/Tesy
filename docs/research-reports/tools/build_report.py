#!/usr/bin/env python3
"""Compile an offline report. Release requires the exact visually reviewed PDF bytes."""
from __future__ import annotations
import argparse
import importlib.metadata
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from reportlib import ROOT, EvidenceError, canonical, check_derived, read, require, safe, sha, validate, verify, publish_no_replace

def version(binary, args):
    require(shutil.which(binary) is not None,'TOOL_REQUIRED: '+binary)
    p=subprocess.run([binary,*args],capture_output=True,text=True,timeout=10,check=False)
    require(p.returncode==0,'TOOL_VERSION_FAILED: '+binary)
    return p.stdout.strip()

def compile_one(root, v):
    runs=safe(root,'_build');runs.mkdir(exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix=v['meta']['id']+'-',dir=runs))
    shutil.copy2(v['folder']/'report.tex',work/'report.tex')
    for name in ('sections','generated'): shutil.copytree(v['folder']/name,work/name)
    for name in ('template','shared'): shutil.copytree(root/name,work/name)
    env={**os.environ,'SOURCE_DATE_EPOCH':str(v['meta']['build_epoch']),'FORCE_SOURCE_DATE':'1',
         'TZ':'UTC','LC_ALL':'C.UTF-8','TEXINPUTS':str(work/'template')+':'+str(work/'shared')+':',
         'BIBINPUTS':str(work/'shared')+':','openin_any':'r','openout_any':'p'}
    command=['latexmk','-norc','-lualatex','-halt-on-error','-interaction=nonstopmode',
             '-file-line-error','-latexoption=-no-shell-escape','-recorder','report.tex']
    try:
        p=subprocess.run(command,cwd=work,env=env,capture_output=True,timeout=180,check=False)
    except subprocess.TimeoutExpired as exc:
        (work/'build.log').write_bytes((exc.stdout or b'')+(exc.stderr or b''))
        raise EvidenceError('TEX_TIMEOUT: '+str(work)) from exc
    log=p.stdout+b'\n'+p.stderr;(work/'build.log').write_bytes(log)
    require(p.returncode==0 and (work/'report.pdf').is_file(),'TEX_BUILD_FAILED: '+str(work))
    text=(work/'report.log').read_text(errors='replace')
    for pattern in (r'There were undefined references',r'Citation .* undefined',r'Reference .* undefined',
                    r'Overfull \\[hv]box',r'Missing character:',r'destination with the same identifier',r'referenced but does not exist'):
        require(re.search(pattern,text) is None,'TEX_LAYOUT_OR_REFERENCE_GATE: '+pattern+'; '+str(work))
    deps={}
    for line in (work/'report.fls').read_text(errors='replace').splitlines():
        if not line.startswith('INPUT '): continue
        p=Path(line[6:]);p=(p if p.is_absolute() else work/p).resolve()
        if p.is_file() and not p.is_relative_to(work) and str(p) not in deps:
            deps[str(p)]=sha(p.read_bytes())
    return (work/'report.pdf').read_bytes(),log,[{'path':p,'sha256':h} for p,h in sorted(deps.items())],work

def build(root, report_id, mode='draft', source_mode='snapshot', repo=None, check_reproducible=False):
    v=verify(root,report_id,source_mode,repo);check_derived(v);m=v['meta']
    require(mode in ('draft','release'),'UNKNOWN_BUILD_MODE')
    audit_path=v['folder']/'audit.json';audit_hash=None
    if mode=='release':
        audit=read(audit_path);validate(root,'audit',audit)
        require(m['editorial_state']=='REVIEWED' and audit['status']=='REVIEWED','EDITORIAL_REVIEW_REQUIRED')
        require(audit['inputs_sha256']==v['lock']['inputs_sha256'],'AUDIT_STALE')
        require(audit['claims_reviewed'] and audit['all_pages_visually_reviewed'] and not audit['open_blockers'],'AUDIT_BLOCKED')
        require(v['claims'] and v['sources'],'RELEASE_REQUIRES_EVIDENCE');audit_hash=sha(audit_path.read_bytes())
    tools={'python':sys.version,'jsonschema':importlib.metadata.version('jsonschema'),
           'lualatex':version('lualatex',['--version']),'latexmk':version('latexmk',['-v']),'biber':version('biber',['--version']),
           'platform':platform.platform(),'locale':'C.UTF-8','source_date_epoch':m['build_epoch']}
    parent=safe(root,'published/'+report_id+'/v'+m['version']);parent.mkdir(parents=True,exist_ok=True)
    dest=parent/('release' if mode=='release' else 'draft-'+v['lock']['inputs_sha256'][:12])
    require(not dest.exists() and not dest.is_symlink(),'PUBLICATION_EXISTS: '+str(dest))
    pdf,log,deps,work=compile_one(root,v)
    if mode=='release': require(sha(pdf)==audit['reviewed_pdf_sha256'],'PDF_DIFFERS_FROM_REVIEWED_ARTIFACT')
    other_hash=None;repro='NOT_RUN'
    if check_reproducible:
        other,_,deps2,work2=compile_one(root,v);other_hash=sha(other)
        if pdf!=other:
            (work/'reproducibility-failure.json').write_bytes(canonical({'first':sha(pdf),'second':other_hash,'second_build':str(work2)}))
            raise EvidenceError('PDF_BYTE_DIFFERENT: '+str(work)+' / '+str(work2))
        require(deps==deps2,'TOOLCHAIN_INPUTS_CHANGED_DURING_BUILD');repro='BYTE_REPRODUCIBLE_IN_RECORDED_ENVIRONMENT'
    after=verify(root,report_id,source_mode,repo)
    require(after['lock']==v['lock'],'INPUTS_CHANGED_DURING_BUILD');check_derived(after)
    if audit_hash: require(sha(audit_path.read_bytes())==audit_hash,'AUDIT_CHANGED_DURING_BUILD')
    manifest={'schema_version':'tesy-release-v1','report_id':report_id,'version':m['version'],'inputs_sha256':v['lock']['inputs_sha256'],
              'mode':mode,'scientific_state':m['scientific_state'],'source_integrity':'PASS','derivation':'PASS','pdf_build':'PASS',
              'pdf_reproducibility':repro,'experimental_reproduction':'NOT_RUN','raw_data_availability':'NOT_ACCESSED',
              'pdf_sha256':sha(pdf),'pdf_sha256_second':other_hash,'toolchain':tools,'loaded_tex_files':deps,
              'audit_sha256':audit_hash,'build_log_sha256':sha(log),'pdf_bytes':len(pdf)}
    validate(root,'release',manifest);stage=Path(tempfile.mkdtemp(prefix='.publish-',dir=parent))
    try:
        for name,data in {'report.pdf':pdf,'release.json':canonical(manifest),'evidence-lock.json':canonical(v['lock']),'build.log':log}.items():
            with (stage/name).open('xb') as f: f.write(data);f.flush();os.fsync(f.fileno())
        publish_no_replace(stage,dest)
    except BaseException:
        if stage.exists(): shutil.rmtree(stage)
        raise
    return dest

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report');p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--mode',choices=['draft','release'],default='draft');p.add_argument('--source-mode',choices=['snapshot','git'],default='snapshot')
    p.add_argument('--repo',type=Path);p.add_argument('--check-reproducible',action='store_true');a=p.parse_args()
    try: print(build(a.root,a.report,a.mode,a.source_mode,a.repo,a.check_reproducible))
    except (EvidenceError,OSError,subprocess.SubprocessError) as exc: p.exit(1,'FAIL: '+str(exc)+'\n')
if __name__=='__main__': main()
