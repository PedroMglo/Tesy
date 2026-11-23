"""Post-C198 fixed transcript, independent holdout and short natural JSON task."""
import re,sqlite3,time
from native64_sql import extract,grade as grade_known,read_only_result
from c2_gate import GateError

HOLDOUT_PROMPT=('SQLite: clientes(cliente_id INTEGER PRIMARY KEY, nome TEXT NOT NULL); '
 'pedidos(pedido_id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL REFERENCES clientes, '
 'estado TEXT NOT NULL CHECK(estado IN (\'ok\',\'cancelado\')), valor INTEGER NULL); '
 'reembolsos(reembolso_id INTEGER PRIMARY KEY, pedido_id INTEGER NOT NULL REFERENCES pedidos, valor INTEGER NULL). '
 'Todas as chaves e referências são válidas. NULL em valor significa zero. '
 'Devolve uma única query SELECT/WITH: total líquido por cliente = soma dos valores dos pedidos ok '
 'menos TODOS os seus reembolsos; pedidos cancelados e seus reembolsos são excluídos. '
 'Preserva todos os clientes, incluindo os sem pedidos, com total zero; totais negativos são permitidos. '
 'Resultado: cliente_id, nome, total_liquido, ordenado por cliente_id ascendente. '
 'Não duplica o valor de um pedido quando este tem vários reembolsos. '
 'Devolve apenas a query ou um único bloco SQL, sem explicações.')
# Six independent fixtures, fixed before model outputs; no C164 routing/data.
HOLDOUT_FIXTURES=(
 ([],[],[]),
 ([(1,'ana'),(2,'bia')],[],[]),
 ([(1,'ana'),(2,'bia')],[(10,1,'ok',100),(11,1,'ok',100),(12,2,'cancelado',999)],[(1,10,10),(2,10,20),(3,11,5),(4,12,800)]),
 ([(1,'ana'),(2,'bia'),(3,'céu')],[(1,1,'ok',None),(2,2,'ok',0),(3,2,'ok',9)],[(1,1,None),(2,2,0),(3,3,None)]),
 ([(1,'ana'),(2,'ana')],[(1,1,'ok',5),(2,1,'cancelado',20),(3,2,'ok',5)],[(1,1,8),(2,2,20),(3,3,1),(4,3,1)]),
 ([(2,'bia'),(1,'ana'),(3,'céu')],[(8,1,'ok',7),(9,1,'ok',7),(10,3,'cancelado',None),(11,2,'ok',-2)],[(1,8,7),(2,8,0),(3,9,2),(4,9,3),(5,11,None)]),
)

def holdout_expected(fixture):
 clients,orders,refunds=fixture;net={c[0]:0 for c in clients};active={}
 for oid,cid,state,value in orders:
  if state=='ok':net[cid]+=value or 0;active[oid]=cid
 for _,oid,value in refunds:
  if oid in active:net[active[oid]]-=value or 0
 return [(cid,name,net[cid]) for cid,name in sorted(clients)]

def grade_holdout(content):
 start=time.monotonic();query=extract(content);results=[]
 for fixture in HOLDOUT_FIXTURES:
  db=sqlite3.connect(':memory:')
  try:
   db.execute('PRAGMA foreign_keys=ON')
   db.execute('CREATE TABLE clientes(cliente_id INTEGER PRIMARY KEY,nome TEXT NOT NULL)')
   db.execute("CREATE TABLE pedidos(pedido_id INTEGER PRIMARY KEY,cliente_id INTEGER NOT NULL REFERENCES clientes,estado TEXT NOT NULL CHECK(estado IN ('ok','cancelado')),valor INTEGER)")
   db.execute('CREATE TABLE reembolsos(reembolso_id INTEGER PRIMARY KEY,pedido_id INTEGER NOT NULL REFERENCES pedidos,valor INTEGER)')
   for table,rows in zip(('clientes','pedidos','reembolsos'),fixture):
    if rows:db.executemany('INSERT INTO '+table+' VALUES('+','.join('?' for _ in rows[0])+')',rows)
   db.commit();actual=read_only_result(db,query,start,functions={'coalesce','sum','max','ifnull','count','row_number'});want=holdout_expected(fixture)
   if actual!=want:raise GateError('holdout functional result mismatch')
   results.append({'expected':want,'actual':actual})
  except sqlite3.Error as exc:raise GateError('holdout SQL rejected: '+str(exc)) from exc
  finally:db.close()
 return {'PASS':True,'query':query,'fixtures':results,'validator_s':time.monotonic()-start}

JSON_CONTEXT=('Estamos a preparar um serviço fictício de importação de CSV para uma equipa pequena. '
 'Os ficheiros chegam com cabeçalhos instáveis e linhas duplicadas; precisamos de manter '
 'a configuração explícita e os dados no portátil. Nesta conversa não executes código, '
 'não abras portas e não alteres ficheiros. Apenas mantém o contrato de configuração. ')*12
JSON_TURNS=(JSON_CONTEXT+'\nFixa o projeto Lume, funcionamento totalmente local, armazenamento disco e porta18440. '
 'Responde apenas com um objeto JSON com chaves projeto, local, armazenamento e porta, '
 'valores "Lume", true, "disco" e18440.',
 'Atualiza apenas porta para18441. Devolve o mesmo objeto JSON, preservando os restantes campos.')
