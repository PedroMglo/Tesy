#!/usr/bin/env python3
"""Create a no-replace DRAFT/NOT_RUN skeleton; registry is edited separately."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import re
import shutil
import tempfile
from reportlib import ROOT, ID, SECTIONS, EvidenceError, canonical, publish_no_replace, require, safe
HEADINGS=['Síntese executiva','Pergunta de investigação','Contexto','Contrato experimental','Metodologia','Resultados',
          'Experiências falhadas','Interpretação','Limitações','Decisão','Próximo gate','Apêndices']

def create(root,name,base,day):
    require(ID.fullmatch(name) is not None,'INVALID_ID');require(re.fullmatch('[a-f0-9]{40}',base) is not None,'FULL_BASE_COMMIT_REQUIRED')
    dt=datetime.strptime(day,'%Y-%m-%d').replace(tzinfo=timezone.utc)
    parent=safe(root,'campaigns');parent.mkdir(exist_ok=True);dest=parent/name
    require(not dest.exists() and not dest.is_symlink(),'CAMPAIGN_EXISTS');stage=Path(tempfile.mkdtemp(prefix='.new-',dir=parent))
    try:
        (stage/'sections').mkdir();(stage/'generated').mkdir()
        meta={'schema_version':'tesy-campaign-v1','id':name,'version':'0.1.0','kind':'campaign','title':'Título por definir',
              'subtitle':'Esqueleto documental sem resultados','date':day,'language':'pt','author':None,'scientific_state':'NOT_RUN',
              'editorial_state':'DRAFT','state_evidence':None,'document_base_commit':base,'evidence_snapshot_commits':[],
              'build_epoch':int(dt.timestamp()),'experimental_reproduction':'NOT_RUN','raw_data_availability':'NOT_ACCESSED',
              'scope_note':'Preencher apenas com protocolo e evidência realmente disponíveis.','included_reports':[]}
        spec={'schema_version':'tesy-evidence-spec-v1','authorities':{},'source_contracts':[],'metrics':[],'claims':[],'checks':[],'datasets':[]}
        (stage/'campaign.json').write_bytes(canonical(meta));(stage/'evidence-spec.json').write_bytes(canonical(spec))
        shutil.copy2(root/'template/campaign-template.tex',stage/'report.tex')
        for i,(section,title) in enumerate(zip(SECTIONS,HEADINGS)):
            (stage/'sections'/(section+'.tex')).write_text(('\\clearpage\n' if i==1 else '')+'\\section{'+title+'}\n\\EvidenceNotRun{Protocolo e fontes por preencher; nenhum resultado é presumido.}\n')
        (stage/'audit.md').write_text('# Auditoria\n\nDRAFT. Sem revisão.\n');(stage/'CHANGELOG.md').write_text('# 0.1.0\n\nEsqueleto inicial sem resultados.\n')
        publish_no_replace(stage,dest)
    except BaseException:
        if stage.exists():shutil.rmtree(stage)
        raise
    return dest

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('name');p.add_argument('--base-commit',required=True);p.add_argument('--date',required=True);p.add_argument('--root',type=Path,default=ROOT);a=p.parse_args()
    try:print(create(a.root,a.name,a.base_commit,a.date));print('Registar explicitamente em registry.json antes de derive/build.')
    except (EvidenceError,OSError,ValueError) as exc:p.exit(1,'FAIL: '+str(exc)+'\n')
if __name__=='__main__':main()
