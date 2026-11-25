# Libertar o worker e entregar o expert pelo produtor

**GO na fixture do manager C305. O ganho para a conversa 120B continua INCONCLUSIVE.** Em quatro processos B, a procura que encontrou o expert 1 em leitura manteve a reserva do slot e libertou a quarta thread. Essa thread aceitou o expert 4 antes de qualquer um dos três produtores terminar. O próprio produtor de 1 fez as três cópias e publicou a geração reservada. No controlo A a quarta thread esperou e o produtor de 2 teve de terminar antes de 4 ser aceite.

Com o terceiro produtor livre aos 350 ms, o adiantamento do remap chegou a finish nos dois pares. Com o mesmo produtor livre aos 1400 ms, o remap adiantou-se em ambos e finish terminou menos de 1 ms depois do respetivo controlo. O sinal inverteu-se ao incluir cleanup. Os tempos de serviço da primeira componente eram impostos prospectivamente. Estes intervalos só quantificam esse ensaio. [Pré-registo](protocolo.md) · [Recibo dos oito braços e das falhas](confirm01.json)

| Agenda de 3 | Ordem | Remap desde t0 (ms) | Finish desde t0 (ms) | A − B no remap / finish (ms) |
|---|---|---:|---:|---:|
| 350 ms | A1 | 959,073 | 959,088 | |
| 350 ms | B2 | 697,375 | 697,389 | +261,698 / +261,698 |
| 350 ms | B3 | 682,138 | 682,150 | +276,841 / +276,848 |
| 350 ms | A4 | 958,979 | 958,998 | |
| 1400 ms | A1 | 960,003 | 1427,778 | |
| 1400 ms | B2 | 679,877 | 1428,441 | +280,126 / −0,663 |
| 1400 ms | B3 | 680,439 | 1428,937 | +279,325 / −0,987 |
| 1400 ms | A4 | 959,764 | 1427,950 | |

Por braço, depois do aquecimento, três produtores leram três componentes cada e a procura direta leu outras três. Os doze componentes somam 52 876 800 bytes lógicos. Seis cópias da cache somam 26 438 400 bytes. A referência independente conferiu os doze componentes dos destinos, incluindo os residentes, e os quatro processos de cada política entregaram o mesmo digest, ordem de ranks, slots e gerações. Cada journal teve 66 eventos e quatro threads distintas. A maior diferença entre um deadline dos portões e a abertura observada foi inferior a 1 ms (tolerância de 150 ms). O relógio parte de t0, antes do remap, e termina quando finish regressa. A compilação e a escrita dos ficheiros de verificação estão fora desses intervalos.

**Segurança observada.** No erro injetado EIO a primeira componente do ticket anexado falhou. O produtor rejeitou a continuação, acordou os consumidores, conservou o slot por publicar e deixou zero claims. Na injeção de geração obsoleta, as três leituras terminaram. O produtor rejeitou a geração 1 e conservou o claim do novo dono na geração 2. Nos dois processos a nova entrada em scope foi recusada, finish propagou o erro e quatro workers terminaram. Estes dois casos exercitam a reserva e a fila nativas diretamente para observar o estado do manager quando falha. O callback do grafo abortaria o processo nesse caminho. Recuperar e servir o pedido seguinte depois de uma falha fica fora da prova.

**Interpretação para a próxima decisão.** O candidato guarda no máximo um registo por ticket C305, dez no total. Enquanto a leitura está em voo o destino mantém o claim. O produtor valida scope, call, camada, expert, ticket e geração sob o mutex e usa as mesmas cópias para publicar. A fixture prerreserva a mesma população de previsões nos dois braços. Na execução do predictor ligado ao grafo, a thread que volta ao loop também pode aceitar uma previsão adicional se a fila de procuras estiver vazia. Um avanço da barreira só conta se chegar ao fim da fase com as leituras, cópias, cancelamentos e cleanup cobrados. O target assume routing, ordenação e confirmação dos tokens.

A admissão seguinte exige observar o trabalho emergente da fila, validar a neutralidade do observador e comparar a política ligada/desligada no mesmo backend e um R0 contemporâneo. Para os pares C318, a via histórica de +15% exige reduções condicionais de 17,62% nominal e 18,02% código no decode do candidato com prefill fixo. Os ganhos necessários por par são 1,710/1,715 s e 2,055/2,197 s. O saldo admissível de custos adicionais em cada par é o ganho de parede bruto até ao fim do decode menos a respetiva redução exigida, em segundos por pedido. O bruto integrado continua desconhecido. As proteções do outro caso, sinais dos pares, fases e total continuam no [avaliador do controlo](../README.md#c318-trace-off).

## Reproduzir

Checkout limpa Tesy `486d7b049bf451eb15f1dd17dcbfe3789c819f46`, árvore `a705323d3eda4c627b4da71482b0ee274cb3d83f`. O [protocolo](protocolo.md) foi commitado em `35507e0f` antes do candidato. O runner verifica os blobs C305, as fontes instrumentadas do [controlo bloqueante](../manager/README.md), o DSO CPU pinado e o diretório de saída novo.

```sh
python3 -m unittest discover -s research/worker-release-20261124/continuacao
python3 -B research/worker-release-20261124/continuacao/run.py \
  --backend "$TESY_C305_BACKEND" --ggml-base "$TESY_GGML_BASE" \
  --new-output-dir "$TESY_NEW_OUTPUT_DIR"
```

A confirmação alocou 112 222 208 bytes antes da escrita do recibo. O pico de RSS foi 391 372 KiB na compilação e 291 320 KiB nos oito braços normais. O ensaio usou a CPU e um ficheiro esparso sintético num volume local, sem pesos ou GPU. O SHA-256 do recibo é `b7080688efa2b9e8b92031be81fa980f7b557e953590e65229bd14ec2982e3ab`. A exploração r01 terminou em **FAIL** porque a agregação não devolveu o campo decision. O recibo fica preservado com SHA-256 `aaf34d4aa0cadab53a7b41323a1b27ea0a42d10ffe3e2c84e2bdcb9a190002f5`. A confirmação criou nova saída, corrigiu o contrato do recibo e verificou a rejeição de um reinício após erro. Os dois braços negativos de r01 não tinham essa observação.
