# Ordenar as procuras já elegíveis no NVMe

**INCONCLUSIVE no screen de serviço.** Ordenar os mesmos nove e oito experts procurados em duas waves do prefill ajudou no par AB e perdeu no par BA. Só um dos dois pares passou o critério congelado. Os 15 preloads conservaram a ordem e os mesmos 96 componentes passaram a verificação de payload nos quatro braços. A fixture termina aqui. R0, M3 PARTIAL e M4 NOT_MET conservam a decisão de produto. [Pré-registo e critérios](protocol.md) · [Recibo e hashes de todos os raws](evidence-20261125-r1/receipt.json)

| Braço | Última demanda CPU14 (ms) | Última demanda CUDA25 (ms) | Soma das duas janelas (ms) | Serviço dos 96 preads (worker-ms) | Soma dos drains (ms) |
|---|---:|---:|---:|---:|---:|
| FIFO 1 | 98,728 | 55,494 | 154,222 | 897,160 | 237,759 |
| Ordenado 2 | 72,868 | 54,799 | 127,667 | 787,775 | 210,620 |
| Ordenado 3 | 70,693 | 55,370 | 126,063 | 754,542 | 200,354 |
| FIFO 4 | 68,479 | 54,413 | 122,892 | 742,340 | 197,353 |

No par FIFO1→ordenado2 a soma até às últimas demandas caiu **17,22%**, o serviço agregado **12,19%** e o drain **11,41%**. No par FIFO4→ordenado3, os três indicadores pioraram **2,58%**, **1,64%** e **1,52%**. A CPU14 sozinha variou de +26,19% a −3,23%, a CUDA25 de +1,25% a −1,76%. Com dois pares preservamos a dispersão individual. Em particular, os 5,1150% do replay do prefill pressupunham uma redução uniforme em todas as 1 177 gerações. A última demanda da fixture mede só a leitura dos lotes de CPU14 e CUDA25 no host.

Todos os braços pediram 423 428 096 B alinhados para 423 014 400 B lógicos. O disco do sistema reportou exatamente 827 008 setores de 512 B lidos e zero escritos em cada janela de braço. O kernel submeteu o mesmo volume de leituras em cada um. O estado dos controladores e caches do dispositivo continua desconhecido. A amostra do contador `busy_ms` no braço 3 avançou 460 ms, incluindo 334 ms atribuídos à janela CUDA25 que durou cerca de 74 ms. Preservámos essa leitura e usámos o relógio monotónico do processo para medir os intervalos do critério.

### O que distingue o primeiro braço

**DIAGNÓSTICO pós-resultado.** Nos dois controlos FIFO, as quatro primeiras leituras gate da CPU14 procuraram os mesmos experts 19, 112, 45 e 1. Em FIFO1 consumiram 130,771 worker-ms e a janela do primeiro início ao último retorno mediu 36,065 ms. Em FIFO4 os valores foram 32,592 worker-ms e 11,360 ms. Nos braços ordenados, as primeiras quatro leituras referiram-se aos experts 0, 1, 11 e 18 e as suas janelas foram 11,200/11,026 ms. Esta diferença entre controlos idênticos oferece uma explicação alternativa ao ganho do primeiro par. O tempo das primeiras quatro leituras sobrepõe-se às leituras seguintes dos workers que acabaram mais cedo. Não se subtrai essa janela para corrigir o resultado. [Recibo diagnóstico e identidades](onset-evidence-20261125/receipt.json)

A fixture iniciou o primeiro braço depois de uma janela de 60 s sem leitura dos pesos. No C135, o tile 0 da chamada de 148 já tinha terminado **67 gerações e 201 leituras** antes da CPU14. Entre o último READ_END da CPU13 (expert 90, componente up) e o primeiro READ_BEGIN da CPU14 passaram **21 919 µs**. Fica por identificar se a latência inicial depende do estado do SSD, do host ou de outra condição de entrada. O menor teste que poderia mudar a decisão teria de condicionar ambos os tratamentos a um mesmo predecessor observado e ao mesmo intervalo de entrada, cobrar essa preparação no orçamento total e registar estado/contadores do dispositivo. Um novo par sem essa observação repetiria a ambiguidade. A avaliação em mais camadas e pedidos, a integração e o tempo até conteúdo final ficam NOT_RUN.

### Custo e reprodução

**MEDIDO no portátil**, checkout limpa `4551ca9b15553e0280bc1ee891a9372400feeff3`, política C55 r3, inventário próprio 61 amostras/60,186 s. A unidade correu 63,854 s e consumiu 10,248 CPU-s, 327 606 272 B de pico, swap zero. Mínimo de RAM disponível nos braços 26 603 159 552 B e máximos observados nesses braços CPU 56,875 °C, GPU 43,09 °C, NVMe 36,85 °C. A energia ficou desconhecida. O executor físico abriu o GGUF com O_DIRECT no NVMe, fez zero forwards e não submeteu trabalho à GPU. A unidade temporária terminou normalmente, inativa e sem PID após a recolha. Os 131 398 B de raws originais estão na raiz privada persistente da identidade `qualification-prefill-io-order-20261125r1` no portátil. O recibo público indica os tamanhos e hashes de cada ficheiro.

```sh
python3 -B research/qualification-retake/prefill_io_order/compact.py \
  --raw-dir "$TESY_PREFILL_ORDER_RAW" --new-output-dir "$NEW_COMPACT"
python3 -B research/qualification-retake/prefill_io_order/onset.py \
  --raw-dir "$TESY_PREFILL_ORDER_RAW" --trace "$TESY_C135_TRACE" --new-output-dir "$NEW_ONSET"
```
