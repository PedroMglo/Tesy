# Que geração terminou a espera pelo remap?

**TRACE_DERIVED.** Em 110 das 133 observações com quatro trabalhos atribuídos e uma cabeça FIFO já elegível para ler ou copiar, a geração dessa cabeça foi a última a publicar no seu router. O sinal concentra-se nas leituras diretas. Foram as últimas em 106 de 115 casos, contra 4 de 18 cópias READY. Cada braço observa rotas distintas entre as suas próprias cabeças elegíveis. Os braços repetem workloads e os episódios não constituem pedidos independentes. [Protocolo](protocolo.md) · [Recibo por braço](receipts/barrier.json)

| C317 trace-ON | Cabeça elegível e última / elegíveis | Leituras diretas últimas / elegíveis | Cópias READY últimas / elegíveis | Entre os dois accepts, mediana das leituras diretas últimas (ms) | Entre penúltima e última publicação, mediana das leituras diretas últimas (ms) |
|---|---:|---:|---:|---:|---:|
| nominal153-2 | 18 / 26 | 18 / 20 | 0 / 6 | 6,536 | 17,086 |
| nominal153-3 | 21 / 27 | 20 / 23 | 1 / 4 | 6,649 | 15,603 |
| code153-2 | 34 / 39 | 34 / 36 | 0 / 3 | 3,776 | 16,691 |
| code153-3 | 37 / 41 | 34 / 36 | 3 / 5 | 5,011 | 16,432 |

A geração bloqueada e a cabeça pertenciam à mesma rota. O auditor identifica o último P10 entre o início P11 e o fim P12 da espera desse router. A geração identificada foi a última dependência de payload a ficar residente nesta execução. O retorno do remap ainda exige reacquirir o mutex e concluir o callback. A distância entre P5 da geração bloqueada e P5 da cabeça mede quanto passou até ao seu despacho observado. O avanço da cabeça se o primeiro worker puder libertar-se continua desconhecido. O segundo intervalo mede quanto passou entre as duas últimas publicações P10. Nas quatro cópias READY que publicaram por último, só decorreram 30–62 µs entre as publicações. Os dois intervalos usam o journal primário.

Uma leitura direta antecipada concorreria pelo NVMe com os produtores em voo. O serviço, os instantes das cópias e a ordem de publicação poderiam mudar. Atribuir uma poupança exigiria preservar bytes e trabalho em quatro workers, medir o serviço sob essa concorrência e seguir cada dependência até à última barreira e cleanup do pedido. As observações não medem o efeito dessa continuação nos 32 forwards ou no cliente. O nominal C317 permanece diagnóstico e os gates de custo C318 usam os pares trace-OFF definidos originalmente. A decisão de latência continua INCONCLUSIVE.

## Reprodução

O recibo das cabeças tem SHA-256 0433bed283cec04478b136fced1461ac717d28b41d5fc5422851a7695bd69599. O auditor verifica este hash e o manifesto local, valida os oito raws C317 antes de os interpretar e reconcilia todas as classes de cabeça por braço. A unidade não carrega modelo nem usa GPU.

```sh
unit=research/worker-release-20261124
python3 "$unit/barreira/barrier.py" --raw-dir "$TESY_C317_RAW" --head-receipt "$unit/receipts/head.json" --new-output-dir "$out/barreira"
python3 -m unittest discover -s "$unit"
```

O pré-registo tem SHA-256 a6d7b58dde1c73201da5547fa16c94bf81daeee51af89271df3ff093ecea341a. Três execuções deram o mesmo recibo de 7 546 B, SHA-256 525bb332998474040b5ac52a34dad3d99baff73ec94502d5d614fb2db031fe46. As duas primeiras demoraram 0,77 e 0,92 s, usando até 65 224 KiB RSS. Os 13 testes da unidade passaram. Os casos novos cobrem a última publicação em cada uma das três gerações, empate no relógio, rota diferente, cabeça duplicada, barreira incompleta, recibo alterado e destino já existente.
