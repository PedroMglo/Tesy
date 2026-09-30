"""Generate native64 probes from exact C127/reference source with audited anchors."""
import argparse,difflib,hashlib,json
from pathlib import Path

def replace(source,old,new,count=1):
    if source.count(old)!=count:raise ValueError('source anchor count changed: '+old)
    return source.replace(old,new)

def capture_source(source):
    for a,b,n in [
        ('chunk < 6','chunk < 3',1),('chunk == 5','chunk == 2',4),
        ('29 : 32','61 : 64',2),('chunk == 4','chunk == 1',2),
        ('prefill128','prefill64',2),('chunk*32','chunk*64',2),
        ('state.chunk_by_layer[35] < 5','state.chunk_by_layer[35] < 2',1),
        ('cp.n_ubatch = 32;','cp.n_ubatch = 64;',1),
        ('state.chunk_by_layer[static_cast<size_t>(layer)] == 5','state.chunk_by_layer[static_cast<size_t>(layer)] == 2',1),
        ('six internal microbatches','three internal microbatches',1)]:source=replace(source,a,b,n)
    return source

def reference_source(source):
    for a,b,n in [('prefill128','prefill64',4),
                 ('prefill64\\t35\\t4\\t128','prefill64\\t35\\t1\\t64',1),
                 ('? 32 :','? 64 :',1),('(layer == 35 ? 1 : 29)','(layer == 35 ? 1 : 61)',1)]:source=replace(source,a,b,n)
    return source

def prepare(out):
    out.mkdir(parents=True,exist_ok=False);records={}
    for name,path,generate in [('capture','tools/c127_slots40_boundary_capture.cpp',capture_source),('reference','tools/c7_layer_reference.cpp',reference_source)]:
        parent=Path(path).read_text();text=generate(parent);target=out/(name+'.cpp');target.write_text(text)
        (out/(name+'.patch')).write_text(''.join(difflib.unified_diff(parent.splitlines(True),text.splitlines(True),fromfile=path,tofile=str(target))))
        records[name]={'parent':path,'parent_sha256':hashlib.sha256(parent.encode()).hexdigest(),'generated_sha256':hashlib.sha256(text.encode()).hexdigest(),'source':str(target),'patch':str(out/(name+'.patch'))}
    (out/'generation.json').write_text(json.dumps(records,indent=2)+'\n')
    return records
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();print(json.dumps(prepare(a.output),indent=2))
