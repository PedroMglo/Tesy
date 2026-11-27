# Começar o cálculo quando cada expert está pronto

**NO_GO para construir um backend com base nesta sobreposição e num banco fixo de 353 experts, aos custos observados.** O novo operador produziu um ganho exato numa camada do portátil. No pedido completo, restringir o serviço às camadas que já podem conhecer a sua rota elimina a folga de 136 ms da primeira projeção. Mesmo uma escolha retrospetiva com acesso direto aos pesos tem um piso de 10,105 s em P106. Combinar mudanças pode reabrir a hipótese. A testemunha combinada precisa de recuperar 516,436 ms no cliente e de antecipar uma seleção que as três políticas causais ensaiadas ainda não produzem. M3 PARTIAL e M4 NOT_MET. [Experiência física, limites e próxima decisão](layer/README.md) · [Proposta por perfil de hardware](../../docs/architecture/0005-execucao-local-por-perfil.md)

## O que a mudança teria de vencer

P97 e P106 são dois processos do portátil com o mesmo routing, sequência de IDs, pesos e NVMe. O turno reutilizou 2 044 posições, processou 153 e gerou 47 IDs. Os limites nas tabelas são **TRACE_DERIVED**. Cada linha conserva o exterior das chamadas e dá gratuitamente os custos novos de coordenação, memória transitória e sincronização. Os números MEDIDOS dos dois controlos trace-ON reproduzem os recibos ao nanossegundo. Os pares com trace desligado que mediram o layout do pack são outras execuções. [Controlo operacional e fases medidas](../qualification-retake/packed_nvme_manifest/server_profile/conversation/ordens.md)

| Cenário | Primeiro final P97 / P106 (s) | Decode P97 / P106 (s, 47 IDs) |
|---|---:|---:|
| Controlo medido com o observador | 18,326 / 19,529 | 8,947 / 9,214 |
| Sobrepor integralmente callbacks e trabalho restante por chamada | 12,569 / 13,161 | 6,813 / 6,789 |
| Cobrar só o serviço imprescindível de quatro workers, sobrepor o restante | **10,658 / 11,416** | 6,745 / 6,738 |
| Conceder custo zero a todos os SET no mesmo limite | 9,808 / 10,696 | 6,095 / 6,024 |
| Conceder custo zero a todos os READ no mesmo limite | 5,911 / 7,171 | 2,278 / 2,576 |

Cada processo reconciliou 2 987 callbacks, 7 012 quartetos e 2 354 reservas. O limite permissivo cobra 827 das 1 263 reservas de prefill, as 1 067 anteriores ao primeiro final no decode e as 24 posteriores. Oferece gratuitamente as outras 436. As 44 avaliações antes do primeiro final contam nos dois relógios. O exterior das chamadas custa 151 / 793 ms ao primeiro final e 141 / 140 ms ao decode. Em P106, a seleção observada antes do POST inclui até 646,428 ms. Mesmo retirando todo esse tempo, o piso sem banco seria 10,769 s. O preço READ+SET por job teria de descer a **78,6867%** do observado, ou menos, para que ambos os pisos abrissem margem conjunta conservando o restante trabalho. A duração dos SET termina no host. O trabalho de um worker e o tempo de espera do cliente têm denominadores diferentes. [Protocolo](protocol.md) · [Contagens, preços e saldos](overlap-result.json)

## Em que memória caberia outra execução?

A alternativa guarda uma fração idêntica dos pesos codificados de cada expert. O controlo guarda experts inteiros escolhidos no primeiro turno. Os orçamentos são iguais. Sob o modelo favorável de custo proporcional aos bytes, com divisibilidade perfeita e acesso imediato, a fração uniforme precisa de pelo menos **12 994 473 600 B (12,10 GiB)** de payload adicional para caber nos dois prazos nos dois processos. Se todos os SET continuarem pagos, o mínimo sobe para **14 554 339 200 B (13,55 GiB)**. Estes números correspondem a 983 e 1 101 equivalentes de um expert. Um equivalente a menos já falha em P106. O orçamento testado é **4 666 377 600 B (4,35 GiB)**. Os valores referem-se a esta forma de colocação, rota e preços. Outro computador precisa de medições próprias de serviço, cálculo e memória livre. [Protocolo de residência](residency-protocol.md) · [Mínimos, inteiro anterior e preços por tier](residency-result.json)

| Com 4,35 GiB e SET pagos | Jobs abrangidos, de 1 918 | Primeiro final P97 / P106 (s) | Decode P97 / P106 (s) |
|---|---:|---:|---:|
| Fração uniforme | 1 918 parciais | 9,999 / 10,958 | 6,292 / 6,291 |
| Últimas vítimas de T1 | 278 | 9,893 / 10,854 | 6,236 / 6,241 |
| Frequência no prefill de T1 | 292 | 10,241 / 11,200 | 6,522 / 6,521 |
| Nova seleção pelo tempo da reserva à publicação | 222 | **10,067 / 11,013** | 6,351 / 6,344 |

A frequência cobriu mais jobs do que a recência e deixou o utilizador à espera mais tempo na projeção. Na política uniforme, o saldo favorável em P97 com SET pagos é só 0,604 ms. A recência e a política uniforme admitem sinais diferentes entre as observações. O replay cobre duas execuções da mesma conversa. Ainda não há evidência de produto fora deste portátil.

## Uma política aprendida no próprio computador

A política nova vê uma vítima só quando os seus pesos ainda estão disponíveis. Acumula por expert a duração da reserva à publicação completa no primeiro turno e mantém até 353 vítimas, com desempate por recência. O selecionador leu exclusivamente os 87 736 registos anteriores ao segundo POST. Entre 4 548 ofertas, admitiu 1 022, repetiu 393 e rejeitou 3 133. Das admitidas, 669 foram depois expulsas. Formar este banco exigiria **13 510 022 400 B** de aquisições durante T1 para 4,35 GiB de capacidade. A avaliação usou outro processo e revalidou a escolha antes de abrir T2. Mesmo concedendo acesso direto gratuito aos pesos retidos, o primeiro final fica em **10,024 / 10,969 s**. **NO_GO desta política e orçamento.** O banco de recência deu um piso menor em ambas as observações. [Implementação](selection.py) · [Seleção, aquisições e braços](selection-result.json)

A proposta inicial pontuava cada expert pelo crédito marginal do seu READ na duração da wave. Ficou **NOT_RUN_RAW_REQUIRED**. No prefixo autenticado há 5 727 reservas e 5 727 publicações. Faltam a procura, o despacho, os eventos de READ e SET e as fronteiras das callbacks. A política por tempo até à publicação foi congelada separadamente e pode incluir espera na fila. O treino nunca consultou o sufixo detalhado. [Método inicial](selection-protocol.md) · [Alternativa observável](selection-observation.md)

## O orçamento de 353 experts permite alguma escolha?

**EXISTS_HEADROOM_ONLY.** Construímos uma única seleção de 353 das 2 829 vítimas realmente oferecidas no primeiro turno. O algoritmo teve acesso aos custos futuros de T2. A seleção comum aos dois processos cobre 512 dos 1 918 jobs cobrados, com 110 no prefill e 402 antes do primeiro conteúdo final no decode. Todos os SET continuam pagos. No mesmo modelo otimista, o primeiro final fica em **9,118 / 9,864 s** e o decode das 47 saídas em **5,447 / 5,249 s**, na ordem P97 / P106. As margens no primeiro final são 882 e **136 ms**. Esse último valor é o máximo que esta testemunha pode pagar em atrasos adicionais comuns até ao primeiro final de P106 se os demais custos e concessões se realizarem. O teto dos ganhos para qualquer banco foi também verificado contra enumeração numa fixture. [Método e prova do teto](existence-protocol.md) · [Testemunha, contagens, custos e digest das chaves](existence-result.json)

A aquisição de cada chave uma vez custaria 4 666 377 600 B em T1. A combinação dá gratuitamente a coordenação e todas as 436 gerações fora do piso e admite sobreposição perfeita entre operações que o grafo real pode serializar. Duas execuções do mesmo histórico deixam a capacidade preditiva em mensagens novas por medir. A prova afasta a objeção de que 4,35 GiB seriam insuficientes para todas as colocações seletivas **neste modelo**. A curva de 12,10–13,55 GiB acima continua a aplicar-se à distribuição uniforme.

**Próxima decisão de arquitetura.** Medir quanto da sobreposição se pode realizar na camada que atrasou o pedido, com a seleção fixada, os READ e SET reais e os resultados reduzidos na ordem do target. Se a diferença para o piso consumir a margem, repetir o limite com os custos obtidos antes de investir em previsão. Se sobrar margem, a observação mínima para o seletor causal é a ligação, antes de T2, entre procura, reserva, worker, READ, SET, publicação e wave. A confirmação exige histórico inédito, proteção de código, KV, logits, recursos e relógios do cliente no mesmo perfil. Outro computador necessita da sua própria calibração.

## Reprodução e orçamento

A base, os dois manifestos e a política de falha estão nos protocolos. O primeiro replay foi executado no commit `c08b7a9a`, o de residência em `daf52bc1` e o causal em `9df0ec5a`. Duas execuções por etapa deram recibos idênticos byte a byte. No portátil os replays de sobreposição duraram 1,21 / 1,18 s, os de residência 2,24 / 2,23 s, as seleções 0,47 / 0,47 s e as duas avaliações 2,53 / 2,51 s. Pico máximo observado nos processos de avaliação 70 804 KiB. Sem novos pedidos, GPU, pesos ou medições de energia. O teste de digest errado preservou FAIL, a origem ausente devolveu NOT_RUN_RAW_REQUIRED e o diretório existente foi recusado.

A cópia local exclusiva `outputs/ready-experts-20261127-01` conserva 11 ficheiros (75 516 B). O digest SHA-256 da lista ordenada de caminhos relativos, tamanhos e hashes em JSON compacto é `f244c9c7310bb493dda93b793f0597a2f3fa7fbf0882bba4d335ddf2b0f8badb`. A prova de existência usou um destino distinto, `outputs/ready-experts-capacity-20261127-01`. Os dois recibos com SHA-256 `babccc24a5f1e767e738d9fcca36088e5e49cff14267c58a31b09a9ec0fbf5b6` demoraram 2,22 / 2,16 s no commit `c363e7a1`, com máximo de 71 472 KiB. A suíte integra dez testes sem modelo desta unidade. A reanálise pós-C320 passou também com os oito ficheiros C317 originais e o verificador da consolidação reabriu as 45 heads.

A variável `TESY_PFJ_ARCHIVE` identifica a cópia privada de `qualification-20261124-nvme-01`. No clone público os testes e os recibos compactos podem ser validados sem essa cópia.

```sh
python3 -IB -m unittest discover -s tests -p 'test_ready_expert*.py'
out=$(mktemp -d)
study=research/ready-experts
arm="$TESY_PFJ_ARCHIVE/part-106/tesy-full-prefix-natural-physical-20261125-r01/ON"
python3 -IB "$study/screen.py" --archive "$TESY_PFJ_ARCHIVE" --new-output-dir "$out/overlap"
python3 -IB "$study/residency.py" --archive "$TESY_PFJ_ARCHIVE" --new-output-dir "$out/residency"
python3 -IB "$study/selection.py" train --t1-arm "$arm" --new-output-dir "$out/plan"
python3 -IB "$study/selection.py" score --archive "$TESY_PFJ_ARCHIVE" --plan "$out/plan/plan.json" \
  --plan-sha256 4564ea13caa0aa4d5c5d7da2da3d47906726a83bc3416b11f93baed39476e3df \
  --new-output-dir "$out/score"
python3 -IB "$study/existence.py" --archive "$TESY_PFJ_ARCHIVE" --new-output-dir "$out/capacity"
```
