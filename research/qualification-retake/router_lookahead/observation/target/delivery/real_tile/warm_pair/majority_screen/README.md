# A maioria estrita absteve-se em todos os destinos CPU cheios

Na chamada de prefill C292 de 189 tokens, **nenhum dos 117 sítios com 40 slots ocupados** tinha um expert ausente previsto por mais de metade das posições. Nesses sítios, aplicar a maioria produziu exatamente as mesmas decisões de emissão que desligar a antecipação. A regra fixa de até quatro ofertas identificava 314 das 1 055 gerações elegíveis e emitia também 140 ofertas sem consumidor. Encerra-se o teste desta regra como forma de conservar acertos quentes e reduzir leituras excedentes nesta população. [Protocolo anterior à contagem](protocol.md) · [Recibo reproduzido](result.json)

| Destino no último E33 | Sítios | Reservas oficiais | Gerações elegíveis | Fixa, ofertas / acertos / falsas | Maioria, ofertas / acertos / falsas |
|---|---:|---:|---:|---:|---:|
| Vazio | 24 | 1 074 | 1 074 | 96 / 96 / 0 | 11 / 11 / 0 |
| Parcial | 3 | 33 | 33 | 12 / 11 / 1 | 0 / 0 / 0 |
| Cheio, 32 posições | 93 | 951 | 796 | 361 / 243 / 118 | 0 / 0 / 0 |
| Cheio, 29 posições | 24 | 302 | 259 | 93 / 71 / 22 | 0 / 0 / 0 |
| **Todos os cheios** | **117** | **1 253** | **1 055** | **454 / 314 / 140** | **0 / 0 / 0** |
| **Total** | **144** | **2 360** | **2 162** | **562 / 421 / 141** | **11 / 11 / 0** |

O estudo cobre os destinos CPU1–24 nas seis tiles, com 4 536 posições de previsão (189 × 24). O último E33 da origem define a decisão. Cada uma das quatro previsões de uma posição dá um voto ao respetivo expert. Ligados READY ou LOADING ficam excluídos. A regra precisa de 17 votos em 32 posições ou 15 em 29. Para o denominador de 2 162, a geração tem de estar ausente na decisão, ser reservada em seguida na própria tile e ter uma demanda efetiva com esse slot e geração. Dos experts previstos sem limite de quatro, 1 765 correspondiam a tais gerações. As 141 ofertas falsas da política fixa careciam de consumidor. [Autoridade E33/E27/E34 e controlo das janelas](../../../../numeric/windows/README.md)

Os 11 acertos da maioria ocorreram em dez sítios vazios de 32 posições. Eram todos demandas da própria wave, ausentes no lookup. No traço de controlo, a leitura e a publicação das 11 aconteceram **depois** da entrada na barreira e até ao regresso. Para as 421 gerações acertadas pela política fixa, 188 eram demandas e 233 preloads para a wave seguinte. Antes ou à entrada da barreira, 105 leituras e 96 publicações já tinham terminado.

| Política nos 144 sítios | Sítios emissores | Gerações certas / ofertas | Origem demanda / preload | Bytes excedentes se todas as ofertas forem lidas |
|---|---:|---:|---:|---:|
| Desligada | 0 | 0 / 0 | 0 / 0 | 0 |
| Fixa | 144 | 421 / 562 | 188 / 233 | 1 864 286 208 |
| Maioria em todas as tiles | 10 | 11 / 11 | 11 / 0 | 0 |
| Maioria só no destino cheio, fixa nos restantes | 27 | 107 / 108 | 75 / 32 | 13 221 888 |

O mesmo cálculo FIFO partilhado a 4,5 GB/s, com 13 221 888 B por janela e as ofertas falsas igualmente cobradas, terminou respetivamente 0/421/11/107 leituras úteis até ao menor entre a aceitação pelo worker e a entrada na barreira. Os dois relógios condicionais deram a mesma conta, tanto com toda a capacidade disponível como eliminando a união das leituras nativas. O crivo mede suporte e verifica prazos. O tempo da projeção, da emissão, das cópias/SET e do dreno numa execução modificada continua por observar.

Nas duas travessias 0→1 já pagas, a maioria também se absteria. Na tile fria, os votos dos quatro experts foram 6/5/5/5 e todos acabaram por ser pedidos. Na tile quente, os votos foram 3/2/2/2 e o único acerto, e20, tinha dois votos. O braço OFF físico dá a referência para emitir zero; uma execução que ainda calcule o preditor e avalie a maioria pode incorrer noutros custos. O resultado não transporta tempos nem decisões para P106. [Travessia fria](../../README.md) · [Travessia quente](../README.md)

## Reprodução

Usar a parte 116 e a Python do ambiente do Tesy. Na pasta desta unidade, executar os comandos abaixo com diretórios de saída novos.

```sh
PY="$TESY_REPO/.venv/bin/python"
"$PY" -IB test_screen.py
"$PY" -IB screen.py --part116 "$PART116" --new-output-dir "$R01"
"$PY" -IB screen.py --part116 "$PART116" --new-output-dir "$R02"
cmp "$R01/receipt.json" "$R02/receipt.json"
cmp "$R01/sites.json" "$R02/sites.json"
cmp "$R01/receipt.json" result.json
```

O protocolo foi congelado em `18ff5249` e o programa em `2fb7ab35`. Os dois processos de revisão levaram 0,46 s cada e usaram 88 744 / 89 128 KiB de RSS máxima. Os recibos resultaram idênticos, SHA-256 `cbe4734d7bb9767fabfbf5060b1f575d351a9dc0c151474904bc785df8f6b1ac`, e as 144 linhas de sítio privadas também, SHA-256 `630dbd1eff4f8b9a05b49e3500103b95c56495673007603a7eb8946abe937813`. A reanálise só abriu metadados e o journal arquivados. Os testes sintéticos cobrem empates, exclusão de residentes, voto na metade, falsa oferta a ocupar o link, primeira geração elegível e publicação tardia.
