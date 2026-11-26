# A seleção dos experts durante o primeiro turno ajuda o segundo?

**NO_GO para as seleções causais por recência e por votos testadas.** No segundo turno nominal, com 353 entradas, a recência ainda precisaria de pelo menos **10,305 s** até ao primeiro conteúdo final, mesmo conservando todas as escolhas até à primeira procura e reduzindo o preço dos READ a 80%. A votação pelas rotas do próprio T1 sobe esse piso para **10,536 s**. O alvo é 10 s. Uma seleção com conhecimento de T2 conseguiria um piso de **9,396 s** já a 100% do preço. Há portanto oportunidade entre os experts efetivamente expulsos, mas nenhuma destas duas regras admite uma fixture de cópias. M3 permanece PARTIAL e M4 NOT_MET. [Protocolo](protocol.md) · [Oito braços, votos e oráculos](evidence/local.json)

## Duas conversas medidas, dois replays da análise local

O R0 usou o GPT-OSS-120B MXFP4 original no NVMe interno. A conversa anterior com PFJ1 ON começou a observação antes do segundo POST. A nova armou a mesma DSO durante o primeiro turno e selou as escolhas antes de T2. Nos dois casos a sessão reutilizou 2 044 dos 2 197 IDs do segundo pedido, processou 5+148 com tiles 32+32+32+32+20 na segunda chamada, validou ambos os conteúdos e emitiu os mesmos 78/47 IDs, incluindo EOG. Na nova sessão, T1 tinha 2 043 IDs de entrada e o selo cobre as 73 chamadas unitárias de 2 047 a 2 119. Ao chegar ao POST estavam identificados os 1 440 slots, sem fila ou claim. [Conversa anterior e respetivo controlo OFF](../conversation/README.md) · [Captura T1](../t1_capture/capture.md)

| Sessão física e turno | Prefill (s) | Decode (s) | tok/s | Primeiro final (s) | Resposta válida (s) |
|---|---:|---:|---:|---:|---:|
| ON anterior, T1 | 62,046 | 19,842 | 3,931 | 81,473 | 81,900 |
| ON anterior, T2 | 10,746 | 10,004 | 4,698 | 20,486 | 20,761 |
| Captura desde T1, T1 | 61,715 | 19,816 | 3,936 | 81,103 | 81,542 |
| Captura desde T1, T2 | 10,755 | 9,994 | 4,703 | 20,540 | 20,818 |

**O comparador entre sessões permanece FAIL_PRESERVED.** As 7 012 linhas de top-4 do T2 coincidiram em ordem e conteúdo, bem como 10 450 DEMAND, 2 354 reservas e 2 354 despachos produtivos. Os 2 679 ENQUEUE e 325 SKIP anteriores passaram a 2 685 e 331. As duas listas de 2 354 publicações e as duas de 7 062 serviços têm o mesmo multiconjunto, com ordem diferente. O diagnóstico R01/R02 reproduziu este resultado. A auditoria local conferiu separadamente o inode atual, as gerações, as filas, os READ e os retornos. Usa exclusivamente os preços e o relógio da segunda sessão. Não se mediu neutralidade temporal do novo gatilho. [Diagnóstico sanitizado](evidence/routes.json) · [Auditor](../t1_capture/diagnose.py)

## Oito braços no T2 atual

**TRACE_DERIVED.** Nas 1 263 admissões primárias do prefill e 1 091 do decode, a retenção copia uma vítima READY ou os bytes de uma nova publicação. «T1» indica uma L2 previamente alimentada pelas expulsões do primeiro turno, em ordem de recência. «Vazia» indica zero entradas ao POST. Os GB são decimais. As duas colunas de tempo são pisos até ao primeiro final na seleção finita ou com sobrevivência perfeita das chaves iniciais. Cada par dá segundos a 1× e a 0,8× do READ. A coluna de cópias soma as duas fases de T2 e dá ingressos na L2 e retornos da L2 ao staging, respetivamente.

| Fonte em T2 | K | Entrada | Hits prefill / decode | Prefill do FD restante (GB) | Finita (s) | Sobrevivência perfeita (s) | Cópias T2 (GB) |
|---|---:|---|---:|---:|---:|---:|---:|
| Vítima | 239 | Vazia | 195 / 198 | 14,131 | 12,277 / 11,023 | 12,277 / 11,023 | 30,589 / 5,195 |
| Vítima | 239 | T1 | 211 / 198 | 13,919 | 12,198 / 10,960 | 11,561 / 10,450 | 30,550 / 5,407 |
| Vítima | 353 | Vazia | 237 / 280 | 13,575 | 12,277 / 11,023 | 12,277 / 11,023 | 29,902 / 6,834 |
| Vítima | 353 | T1 | 269 / 280 | 13,152 | 12,159 / 10,929 | 11,379 / 10,305 | 29,836 / 7,257 |
| Publicação | 239 | Vazia | 32 / 34 | 16,288 | 12,277 / 11,023 | 12,277 / 11,023 | 30,246 / 0,872 |
| Publicação | 239 | T1 | 48 / 34 | 16,076 | 12,198 / 10,960 | 11,561 / 10,450 | 30,034 / 1,084 |
| Publicação | 353 | Vazia | 82 / 48 | 15,626 | 12,277 / 11,023 | 12,277 / 11,023 | 29,400 / 1,718 |
| Publicação | 353 | T1 | 114 / 48 | 15,203 | 12,159 / 10,929 | 11,379 / 10,305 | 28,976 / 2,142 |

Em todos os braços os SET primários continuam a transportar 31 117 996 800 B em T2. A margem de RAM ao ponto de paragem era 5 217 624 064 B. As capacidades 239 e 353 custam 3 212 959 744 e 4 720 263 168 B adicionais com a provisão do protocolo. Só as vítimas a K353 ultrapassam 20% das faltas de decode (280/1 091, 25,66%). Todos os braços falham o critério conjunto. Os tempos de materialização, transporte D2H e coordenação foram concedidos de graça. O recibo conserva bytes por fase e tier, incluindo os retornos alinhados do FD. [Avaliador congelado](../t1_victims/protocol.md) · [Contas completas](evidence/local.json)

## O que os votos mudam

T1 ofereceu 2 156 expulsões READY. São 1 182 chaves CPU e 516 CUDA distintas. As rotas emitiram 7 300 votos CPU e 3 212 CUDA. A K353, a recência instalou 1 530 e 613 slabs CPU/CUDA, num total de 28,329 GB, e deixou 263 e 90 no corte. A K239, instalou 1 538 e 613 e reteve 174 e 65. Estes custos assumem cache vazia no gatilho. Mesmo concedendo um conteúdo inicial desconhecido mais favorável, os mínimos a K353 são 1 272 e 518 cópias, e a K239 são 1 360 e 552. Cada slab contém 13 219 200 B. [Regra de votos](../t1_admission/protocol.md) · [Recibo](evidence/local.json)

A política de votos só admitiu uma vítima com frequência estritamente superior à pior entrada quando a L2 estava cheia. Instalou **568 e 189** slabs CPU/CUDA (10,007 GB) e reteve **280 e 73**. Com captura de vítimas em T2, apenas 21+5 das 757 instalações de T1 serviram até ao fim de T2, contra 28+4 de 2 143 por recência. Ficaram sem uso 547+184 e 1 502+609, respetivamente. Com captura de publicações em T2, serviram 20+5 para os votos e 28+4 para a recência. Os votos pouparam 18,322 GB de cópias em T1, mas conservaram só 79 das 852 chaves de volume obrigatório do prefill, contra 126 por recência.

| T2 a K353, seleção por votos | Hits prefill / decode | FD prefill (GB) | Finita (s), 1× / 0,8× | Sobrevivência perfeita (s), 1× / 0,8× |
|---|---:|---:|---:|---:|
| Vítimas | 262 / 280 | 13,245 | 12,194 / 10,957 | 11,668 / 10,536 |
| Publicações | 107 / 48 | 15,295 | 12,194 / 10,957 | 11,668 / 10,536 |

## Limite da oportunidade observada

Até ao primeiro conteúdo final existem 875 primeiras procuras obrigatórias em 441 grupos. Conservam-se 6,008451991 s fora das callbacks. Em cada grupo, o serviço tem como piso o maior entre a cadeia mais longa de READ e um quarto da soma das cadeias. A soma fria é 6,268797274 s. O budget de prefill ao preço de cenário de 4,5 GB/s é 10 690 306 614 B com **47/6** no contrato M4 e 11 440 306 616 B com **46/6** ao conceder a primeira avaliação. Os dois denominadores e as duas escalas foram fixados antes de pontuar.

| K permitido | Primeiras procuras gratuitas escolhidas | Piso até primeiro final, 1× / 0,8× (s) | Payload prefill da escolha temporal (GB) |
|---|---:|---:|---:|
| 0 | 0 | 12,277 / 11,023 | 11,263 |
| 239 | 239 | 10,052 / 9,243 | 10,166 |
| 353 | 353 | 9,396 / 8,718 | 9,002 |
| Todas as disponíveis, capacidade relaxada | 563 | 8,995 / 8,398 | 4,336 |

Os pisos coincidiram para o conjunto das 1 698 vítimas e para o conjunto ampliado de 2 547 chaves efetivamente acessíveis em T1, que inclui residentes e publicações. Ambos continham só 524 das 852 chaves obrigatórias do prefill. O oráculo usa T2 para escolher antecipadamente entre elas. A K353 a sua folga temporal a 1× é 604 ms. A seleção por recência cobre 170 das 875 procuras mesmo com sobrevivência perfeita e só 29 na política finita. Por votos estes números caem para 112 e 22. Reabrir a via exige uma fonte causal de seleção que melhore estas duas contagens nos grupos caros e ainda cumpra em simultâneo os limites de volume, tempo, hits de decode e RAM. O cenário é exploratório, num segundo turno nominal. O workload de código e uma sessão sustentada precisam das suas próprias medições.

## Proveniência e reprodução

- A máquina da medição usou o Ryzen AI 9 HX 370, RTX 4060 Laptop (8 188 MiB), driver 620.70.06, AC/performance e GGUF original em NVMe/Btrfs. C55 R01 terminou em `FAIL_INVENTORY`, com `nvidia-smi` a devolver 18. C55 R02 registou 61 amostras/60,006 s e aprovou E20. O C118 do processo registou 61 amostras/60,146 s. A DSO PFJ1 carregada tem SHA-256 `911b3be5b529d8e07409c12cf600ca9f7f6182f7a397fc6de265e5ea4be254eb`. O controlo C270 tem SHA-256 `1f332ad437d90c24adf3b88b87ddf0dac8e13b7e87e818d93461ffd281c801b6`.
- A sessão física em `b6023112fab7f4f1f1d3e9f36e54e441293eedcb` chegou a READY em 3,644 s e fechou o envelope em 169,664 s. Pico cgroup 15 720 341 504 B, GPU 6 848 MiB, swap zero, CPU/GPU/NVMe 83,50/58,09/50,85 °C. O supervisor confirmou dois FDs diretos, zero buffered, saída normal por iniciativa do proprietário, scope encerrado e porta disponível. O recibo mantém `FAIL_PRESERVED` pelo comparador histórico, SHA-256 `fc368b04cc5ea6258c05594ab52306c336446f40ab06ea2ec5fe287eabfeef5d`.
- A parte 39 contém C55 e precheck, manifesto SHA-256 `8d6d31605a422b4419de1553068c9c2032e950a61d7b6e25f9e3159b1fc80370`. A parte 40 conserva os 35 ficheiros do processo, manifesto `4907245d68f604c31918d48d50259a60476ef76c1bfc0f848d98db659606b513`. O selo anterior ao POST cobre 47 303 registos, SHA-256 `7c0ef30ca09fca94e1f8be7c178f7a43ab1a9a9f3e9a1fe2e0da792b4fa6a3b2`. A seleção privada reproduzida tem SHA-256 `49a7ab124f20dd4285ac813968092f6210c3c49c85941ccbe7262a24b534732c`.
- O diagnóstico de comparação R01/R02 deu recibos idênticos, SHA-256 `a844c93f4ba39d7ae89ea21b6b2054951b53183f90bf840319f0962f3ed8709f`. A versão pública conserva contagens, igualdade e hashes por classe. O primeiro registo divergente continua privado. [Compacto de rotas](evidence/routes.json)
- O protocolo local está em `03c4123f8b6951bc4a367e4c206f5814df68c08d`. A preparação R01/R02 da versão `84134eecd0752d52ca311c42bd9edc12e0d5540a` selou seleções idênticas. Os primeiros dois scores desta versão falharam antes de calcular as políticas, SHA-256 `f89111ce849a9ee3598e3f07e3adcc8da56ca04e2b8e2ae7cc151bc6ec95a313`. O verificador esperava um motivo de encerramento nulo. A reparação em `ee03dc47bd57d8a7cb95c8e1146fd11fac996ed3` exige o registo real `INTERRUPTED_BY_OWNER`, saída 0 e identidade correspondente no monitor e no owner-stop. Não mudou preços, políticas ou critérios.
- Score R03 levou 1,22 s e 74 668 KiB; R04 levou 1,18 s e 74 392 KiB. Os 62 655 B dos dois recibos são idênticos ao ficheiro publicado, SHA-256 `eb08c93c08201a8074a996a2f898505a452be38f20c03b345df77f9a7a04638a`. Conservaram-se 4 535 reservas, despachos produtivos e publicações, 13 605 READ e 13 605 SET, 121 pares de chamada/retorno e as quatro terminações dos workers na extensão T1+T2 observada. O replay usa CPU, com 120 s/512 MiB por processo, sem novos forwards ou leitura dos pesos. [Recibo integral](evidence/local.json)

Para repetir os mesmos comandos, `SEAL_CODE` designa a checkout limpa de `84134eec` e `SCORE_CODE` a de `ee03dc47`. `ARCHIVE` contém as partes privadas enumeradas acima, `MODEL` aponta para o inode original e `INVENTORY` para o JSON C7 autenticado pelo SHA-256 `2c8ca725f50000bf3177712cfa30d29a809f77f25826b425ea67d8fcbffd6d82`. Usar diretórios novos para cada repetição. O score usa apenas stat do modelo.

```sh
unit=research/qualification-retake/phase_fd/integrated
python3 -IB "$SCORE_CODE/$unit/t1_capture/diagnose.py" \
  --capture-dir "$ARCHIVE/part-40/tesy-pfj-victims-on-20261125-r01" \
  --prior-on-dir "$ARCHIVE/part-37/tesy-phase-fd-c281-on-20261125-r02" \
  --new-output-dir "$NEW_DIAG"
python3 -IB "$SEAL_CODE/$unit/t1_local/source.py" seal \
  --part "$ARCHIVE/part-40" --new-output-dir "$NEW_SEAL"
python3 -IB "$SCORE_CODE/$unit/t1_local/source.py" score \
  --part "$ARCHIVE/part-40" --model "$MODEL" --inventory "$INVENTORY" \
  --prepared-dir "$NEW_SEAL" \
  --prepared-sha256 d5321a870115d479ea5d53016a1796bda52dff0d343984d9aa05e92676a384d4 \
  --new-output-dir "$NEW_SCORE"
```
