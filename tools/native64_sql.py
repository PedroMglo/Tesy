"""Frozen, bounded read-only SQLite validator for native64 useful latency."""
import re
import sqlite3
import time
from c2_gate import GateError

PROMPT = ('A tabela SQLite eventos tem event_id INTEGER, cliente TEXT, atualizado INTEGER, '
          'ingest_id INTEGER e valor INTEGER. Devolve uma única query de leitura que retenha '
          'por event_id a linha com maior atualizado e, em empate, maior ingest_id; depois '
          'some COALESCE(valor,0) por cliente, ordenando por cliente ascendente. '
          'Devolve apenas a query ou um único bloco SQL, sem explicações.')
FIXTURES = (
    (),
    ((1,'ana',1,1,4),(1,'bia',2,1,8),(2,'ana',3,1,None),(3,'ana',2,1,7)),
    ((1,'ana',5,1,10),(1,'ana',5,2,3),(2,'bia',1,1,None),(3,'bia',2,1,-2),
     (4,'ana',1,1,None),(4,'ana',1,2,5)),
    ((1,'z',9,3,None),(1,'z',8,9,10),(2,'a',1,1,6),(3,'a',2,1,4)),
)

def expected(rows):
    best={}
    for r in rows:
        if r[0] not in best or (r[2],r[3])>(best[r[0]][2],best[r[0]][3]):best[r[0]]=r
    totals={}
    for r in best.values():totals[r[1]]=totals.get(r[1],0)+(r[4] or 0)
    return sorted(totals.items())

def extract(content):
    if type(content) is not str or not content.strip() or len(content.encode())>8192:
        raise GateError('SQL response absent/oversize')
    s=content.strip()
    if s.startswith('```'):
        m=re.fullmatch(r'```(?:sql|sqlite)?\s*\n(.*?)\n```',s,re.S|re.I)
        if not m:raise GateError('SQL envelope invalid')
        s=m.group(1).strip()
    if not re.match(r'^(SELECT|WITH)\b',s,re.I):raise GateError('only SELECT/WITH accepted')
    return s

def read_only_result(db, query, start, *, functions=None):
    """Shared bounded executor; caller loads only frozen fixture data beforehand."""
    db.execute('PRAGMA query_only=ON');db.enable_load_extension(False)
    allowed={sqlite3.SQLITE_SELECT,sqlite3.SQLITE_READ,sqlite3.SQLITE_FUNCTION,sqlite3.SQLITE_RECURSIVE}
    funcs=functions or {'coalesce','row_number','sum','max','ifnull'}
    def authorizer(action,a,b,dbname,trigger):
        if action not in allowed:return sqlite3.SQLITE_DENY
        if action==sqlite3.SQLITE_FUNCTION and (b or a or '').lower() not in funcs:return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    db.set_authorizer(authorizer);ticks=[0]
    def progress():
        ticks[0]+=1
        return int(ticks[0]>1000 or time.monotonic()-start>2)
    db.set_progress_handler(progress,100)
    return db.execute(query).fetchmany(100)

def grade(content):
    start=time.monotonic();query=extract(content);results=[]
    for rows in FIXTURES:
        db=sqlite3.connect(':memory:')
        try:
            db.execute('CREATE TABLE eventos(event_id INTEGER,cliente TEXT,atualizado INTEGER,ingest_id INTEGER,valor INTEGER)')
            db.executemany('INSERT INTO eventos VALUES(?,?,?,?,?)',rows);db.commit()
            actual=read_only_result(db,query,start)
            want=expected(rows)
            if actual!=want:raise GateError('SQL functional result mismatch')
            results.append({'rows':len(rows),'expected':want,'actual':actual,'instruction_bound':100000})
        except sqlite3.Error as exc:raise GateError('SQL rejected: '+str(exc)) from exc
        finally:db.close()
    return {'PASS':True,'query':query,'fixtures':results,'validator_s':time.monotonic()-start}
