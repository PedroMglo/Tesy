# Uma política que só oferece com o destino vazio abstém-se em todo o T2

**Zero em 144 sítios CPU +1 de prefill e zero em 1 104 de decode, em cada um dos dois processos naturais com pack.** No início do segundo turno, as 36 camadas tinham os 40 slots em READY. Durante T2, cada uma das 2 354 reservas substituiu diretamente um ocupante READY por uma nova geração LOADING no mesmo slot. Cada uma dessas gerações foi publicada. O número de slots vinculados nunca desceu abaixo de 40 em nenhuma camada, mesmo entre callbacks. [Pré-registo](protocol.md) · [Resultado reproduzido](result.json)

| Fase de T2, por conversa | Sítios de destino CPU +1 | Callbacks nesses destinos | Sítios em CPU0→1 | Sítios CUDA +1 | Elegíveis em CPU ou CUDA |
|---|---:|---:|---:|---:|---:|
| Primeira chamada, 5 posições | 24 | 24 | 1 | 10 | 0 |
| Segunda chamada, 148 posições | 120 | 888 | 5 | 51 | 0 |
| 46 avaliações de decode | 1 104 | 1 104 | 46 | 506 | 0 |

Um sítio corresponde a chamada, microbatch e camada de destino. CPU +1 abrange L1–24 e CUDA +1 L25–35. O verificador conta também L0, que não tem predecessor neste modelo de projeção, e as waves de parking. A última camada respeita a máscara de saída real. Os dois journals têm as mesmas 7 012 linhas de rota confirmada. Mesmo a condição mais permissiva «zero READY» nunca ocorreu. Por exemplo, na camada de destino CPU1 permaneceram sempre pelo menos 25 slots READY em P97 e 24 em P106. [Contagem de cada fase, camada e tier](result.json)

**Consequência para o pedido.** Se o estado mantido de T1 e a agenda primária forem os observados, a regra não inicia nenhum pread em T2. Mesmo concedendo um teste de elegibilidade gratuito, o seu ganho por antecipação é zero. P97 ficou a 18,326 s até ao primeiro conteúdo final e 5,25 saídas/s no decode; P106, a 19,529 s e 5,10 saídas/s. A regra não contribui para alcançar 10 s e 6 saídas/s nesta conversa. O resultado dispensa uma nova captura 5+148 **para esta regra**. Uma política que altere a residência de T1, transporte tickets entre turnos ou esvazie slots de propósito requer contabilizar esse trabalho e as faltas induzidas. [Relógios dos dois turnos T2](../../../../../../../igpu_resident_rank/request_budget/device/pack_native/natural_trace/prefill_retention/repeat/receipt.json)

## Porque basta o snapshot e o que falta para decidir em pools ocupados

O manager C291 `c89c88b3` inicializa o estado dos slots na linha 210 de `src/llama-moe-stream.cpp`. Nas linhas 384–405 escolhe primeiro um slot livre, depois um residente elegível, protegendo LOADING e os slots marcados para conservar. Nas linhas 411–426 remove o índice da vítima, vincula o novo expert e avança a geração sob o mesmo mutex. Essa troca não publica um slot EMPTY a um observador do manager. O worker só publica READY após concluir o carregamento e validar a geração, nas linhas 368–375. A fonte tem SHA-256 `044d8879be19e5c22331a29bf7a273307756de10675b1341ee9d7077e2dabc62`. Conferimos em cada produtor o snapshot de 1 440 slots, os estados de reserva e publicação, os ranks, a vinculação das 108 matrizes aos dois tiers e o join. P106 também reconcilia a fotografia com o estado final selado de T1. [Auditoria do serviço](../../../../../../../igpu_resident_rank/request_budget/device/pack_native/natural_trace/jobs.py) · [Corte nativo de T1](../../../../../../../igpu_resident_rank/request_budget/device/pack_native/full_prefix/audit.py)

A diferença física de sinal entre as duas tiles C292 também envolve ofertas úteis distintas (4/4 e 1/4), composição da fila e competição com a FFN anterior. A ocupação cheia, por si só, não decide quando compensa oferecer. P97/P106 registaram os quatro ranks alvo e o serviço real. Falta a ativação de origem ou a previsão que o produtor realmente emitiria antes da procura, com posição, prioridades, estado primário no mesmo corte e relógios de disponibilidade. Esse é o primeiro dado para crivar **uma regra previamente definida para pools ocupados**. Para identificar o custo das ofertas falsas e das verdadeiras ainda é preciso o contraste de entrega com o mesmo trabalho e estado, incluindo a FFN que disputa os recursos. Os resultados desta unidade não medem esse ganho nem generalizam a outros prompts. [Tile fria](../../README.md) · [Tile quente](../README.md)

## Reprodução

Protocolo `a3911dc3`, código `c3cd0220`. Os testes sintéticos exercitam primário vazio, parcial e cheio, substituição por LOADING e publicação READY, e rejeitam vítima, estado ou geração adulterados. Os dois processos offline sobre os arquivos 97 e 106 produziram compactos idênticos, SHA-256 `0c2e878d4477439d9b104b5d6436ae1a445c08580bb4307b42ecedcd32ca99f3`, em `/tmp/tesy-natural-eligibility-20261125-r01` e `r02`. Ambos concluíram sem falhas. Os únicos dados lidos foram journals, recibos, saídas e logs já arquivados. [Revisor](score.py) · [Contraprovas](test_score.py)

```sh
python3 -IB test_score.py
env LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  prlimit --as=536870912 --cpu=120 timeout 120 python3 -IB score.py \
  --archive /mnt/sdisk-ssd-ext/Tesy/outputs/qualification-20261124-nvme-01 \
  --new-output-dir "$NEW"
cmp "$NEW/receipt.json" result.json
```
