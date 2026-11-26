# Capacidade de duas seleções máximas de decode num único grupo ik

Fixar um único candidato antes de contar: 288 slots reais (2 × 36 camadas
× top-4), em alternativa a 161. Manter share=0 e as duas políticas LRU e
ClassLRU de 7a5d9000. Cada camada observa no máximo quatro chaves no decode;
a capacidade para duas seleções é espaço, não uma garantia de mantê-las
sob ambas as políticas. Reabrir os 74 278 quartetos de T1 e os 7 012 de
T2, poda e ordem de procura do crivo anterior, sem reiniciar entre turnos;
estado ik anterior a T1 vazio por hipótese. Nenhum outro K candidato.

O binário autenticado do estudo anterior rejeita 288 na CLI. Usar uma
representação lógica das filas nativas, atualização CRF binária32 via exp2f
e log2f, desempate e proteção do conjunto demandado idênticos ao header,
sem recompilar. Validar em 161 hits/fills/evictions em **cada sítio** por
igualdade do digest de stdout e das séries com o nativo. Reconciliar as
identidades presentes e as de cada falta. Se a ponte falhar, preservar o
FAIL e não reportar o contrafactual a 288. Não afirmar execução nativa de
288. Comparar por fase as chaves salvas e as adicionalmente perdidas, por
última procura autoritativa (T2 decode anterior, dois ou mais passos de
decode, T2 prefill, T1); no primeiro decode a proc. anterior de prefill tem
categoria própria. Congelar comando/executável e fazer duas reproduções.

Publicar T1 prefill/decode, T2 5/148, decode inicial/global, até à primeira
peça após call 46 e total, hits/fills, payload e taxa H2D necessária sob os
mesmos relógios. Cada fill custa 13 219 200 B, três slabs de 4 406 400 B.
Custo de capacidade usa alocação real por papel em CUDA0, guarda, alinhamento
128 e ceil MiB do pedido. Comparar o delta de VRAM com o maior pico stock
161 nas cargas e HTTP anteriores e o guard total−512 MiB do portátil.
Mostrar o cenário adicional que põe os 159 252 480 B de biases do original
na GPU. Resto igual é hipótese; o grupo, a seleção, os buffers realmente
alocados, workspace, outros utilizadores e picos do ik exigem autoridade
do próprio processo. O teto físico de enlace é 16 GB/s bruto. Preferir
ensaiar 288 se baixarem ambas as exigências para o modelo lógico ClassLRU
e o envelope projetado respeitar o guard mesmo com todos aqueles biases.
Caso contrário preferir 161 e indicar a observação decisiva. Sem GPU, pesos,
compiladores, mudanças do sistema ou ensaios físicos.
