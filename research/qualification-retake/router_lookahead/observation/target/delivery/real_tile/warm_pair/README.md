# Três ofertas falsas na tile quente CPU0→1

**Entregar as quatro previsões atrasou a travessia nas duas ordens: 13,532 ms e 6,146 ms.** O resultado é `NO_GO_TRAVERSAL_TIMING` para a call 1, tile 5 da C292, posições 128–159. Os dois braços acertaram todos os bits dos dois FFN e as mesmas gerações de cada slot. O expert 20 foi lido antecipadamente e consumido; os experts 6, 13 e 21 foram lidos integralmente e expiraram READY. A seleção prospetiva encontrou este caso como o primeiro com falso positivo e gold independente na ordem de tile/camada. [Protocolo](protocol.md) · [Seleção e estado inicial](../next_pair/later_tiles/README.md) · [Revisão dos seis braços](result.json)

| Processo, em ordem de execução | Reposição fora da janela (ms) | FFN0 (ms) | FFN1 (ms) | Finalização e joins (ms) | Fonte→joins (ms) | READ na janela | Processo (s) | Energia do package no processo (J) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| EXACT OFF | 1 052,675 | 139,090 | 45,984 | 3,241 | 190,112 | 32 | 1,357 | 25,538 |
| EXACT ON | 985,914 | 147,714 | 40,924 | 2,775 | 192,814 | 35 | 1,269 | 25,132 |
| TIME OFF | 977,821 | 127,167 | 35,874 | 3,883 | 168,309 | 32 | 1,237 | 23,592 |
| TIME ON | 971,914 | 142,407 | 35,038 | 3,011 | 181,841 | 35 | 1,238 | 23,683 |
| TIME ON | 978,813 | 138,766 | 32,053 | 3,544 | 175,753 | 35 | 1,238 | 23,918 |
| TIME OFF | 976,586 | 128,995 | 35,923 | 3,072 | 169,607 | 32 | 1,221 | 24,652 |

A janela nativa é de parede, desde o início da projeção à saída dos quatro workers após os joins. Inclui projeção e submissão, os dois FFN, verificação entre eles e finalização. Os braços EXACT verificam também os SHA das três slabs de cada leitura nova e os bytes após cada SET. Para os quatro braços TIME, a FFN1 ficou 0,836 e 3,871 ms mais rápida com ON. A FFN0 demorou mais 15,240 e 9,771 ms. A duração desde o lançamento até à observação da saída e a energia do package incluem construção, reposição e limpeza. Os deltas de energia ON−OFF do processo completo foram +0,090 e −0,734 J. Falta uma leitura de energia que delimite a reposição ou só a travessia.

| Ticket no braço ON | Resultado nos três ON | Pread no EXACT (ms) | Pread no primeiro TIME (ms) | Pread no segundo TIME (ms) |
|---|---|---:|---:|---:|
| 1 · expert 6 | Expirou READY | 19,268 | 18,659 | 14,683 |
| 2 · expert 13 | Expirou READY | 11,686 | 18,953 | 18,754 |
| 3 · expert 20 | Consumido READY | 13,088 | 10,277 | 19,013 |
| 4 · expert 21 | Expirou READY | 9,204 | 15,501 | 14,122 |

Nos três ON houve zero descartes antes da leitura, zero cancelamentos durante READING e zero esperas de demanda num ticket em READING. O expert 20 evitou uma leitura ordinária no destino. As três falsas acrescentaram **39 665 664 B por ON**. Nos pares TIME, os seus preads totalizaram 53,113 e 47,558 ms de trabalho somado nos leitores. As respetivas uniões ocuparam 34,466 e 32,885 ms do relógio de parede, inteiramente durante a FFN0. Dessas uniões, 34,377 e 29,359 ms coincidiram com pread ou SET primários da CPU0. As coincidências situam a competição possível no tempo; a duração isolada da competição não foi medida. Os sensores e a fila distinguem as três leituras falsas de uma simples previsão descartada. [Eventos de ticket e verificação por geração](review.py)

**Custos e integridade.** Cada filho repôs 80 gerações com 1 057 751 040 B de pread ao pack e 240 SET, correspondentes a 1 057 536 000 B de pesos primários. O processo autenticou cada slab e releu o destino após o SET. A reposição aconteceu antes do relógio do operador e pode influenciar o estado do NVMe. Dentro da janela, as 28 reservas originais de CPU0 e quatro de CPU1 fizeram 96 SET e 32 publicações nos seis processos individualmente. Os preads da janela passaram de 423 100 416 para 462 766 080 B. As quatro confirmações dos workers precederam o corte. Os 128 ranks ativos por camada, as oito waves, todos os slots/gerações ativos e parking, os 92 160 F32 de cada FFN e o estado terminal foram conferidos contra a preparação selada.

**Recursos e alcance.** A família durou 68,378 s, com 61 amostras da C118 em 60,169 s. A C55 e as identidades do build e do pack estão vinculadas pelo recibo. Pico do cgroup de 1 367 568 384 B sob cap de 4 GiB, swap zero, zero OOM e quatro workers no máximo nas leituras/SET. As 12 observações do monitor tiveram intervalo máximo de 0,719 s e nenhum PID de compute GPU. Máximos CPU/GPU/NVMe de 56,875/42,23/36,85 °C. O package de CPU abrange todo o processo e o consumo energético do NVMe fica desconhecido. O caso frio 0→1, em que as quatro ofertas foram consumidas, teve sinal favorável em ambas as ordens. Os denominadores são duas ordens em cada uma de duas tiles distintas, selecionadas sob condições específicas. Não se mediram uma frequência natural destes acertos, latência ao primeiro conteúdo nem tokens/s. [Caso com quatro ofertas consumidas](../README.md)

**Reprodução.** `warm-tile` e o supervisor foram congelados na revisão física `8a6804ba`. O terminal SHA-256 é `45482afdb6a93914b3050da0bd8fe660b0b01ca8ab0a3ae5544e6a5f3ed29cff`, a preparação é `64c6b08357cc2c03bd0959f417a6e3f905977b5a13be99b70b4b488354b3aa03` e a revisão independente é `ec21431749fbc8c64edae2299c3a4810f4351166f4b66963a4079a185469de3c`. O revisor autentica os stdouts, os seis recibos individuais, o C118 e os 72 ficheiros de inputs pequenos, e reconta o ciclo de vida dos tickets, as transferências e o sinal da decisão. [Preparação](../next_pair/later_tiles/prepare.md)

```sh
python3 -IB "$WARM/test_review.py"
python3 -IB "$WARM/review.py" --raw "$FAMILY" \
  --sha256 45482afdb6a93914b3050da0bd8fe660b0b01ca8ab0a3ae5544e6a5f3ed29cff \
  --prepared "$WARM_INPUT" --new-output-dir "$NEW_REVIEW"
cmp "$NEW_REVIEW/receipt.json" "$WARM/result.json"
```

A reprodução a partir da parte 123 e dos inputs da parte 121 produziu um recibo idêntico byte a byte ao do diretório físico e ao compacto publicado. Foram conferidos os 66 ficheiros da parte 123 (2 147 430 B) e todos os membros do diretório de preparação na parte 121. O manifesto da parte 123 tem SHA-256 `1cfe65912c2835efe7d92aa17440523d46d0e75d5b6f87e0a2a81260fe1cec68`. [Recibo da reabertura](archive.json)
