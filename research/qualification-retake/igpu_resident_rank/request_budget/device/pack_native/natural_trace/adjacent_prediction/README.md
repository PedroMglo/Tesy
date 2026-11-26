# Quanto vale saber os quatro experts da camada anterior?

**65 das 375 primeiras leituras CPU seriam antecipadas com a tabela de coocorrências. A frequência marginal acerta em 39 com o mesmo tráfego.** São propostas simuladas sobre o routing exato do segundo pedido nominal. A política observa apenas os 73 tokens unitários finais do primeiro turno e os quatro IDs de cada token na camada precedente da tile atual. O target continua a escolher as rotas e os quatro ranks. Cada coluna tem a sua população própria. [Protocolo](protocol.md) · [Recibo por braço e chamada](receipt.json)

| Política | Chamada de 5, acertos / 40 | Chamada de 148, acertos / 335 | Propostas | Outras rotas da mesma tile | Sem consumo nessa camada/tile |
| --- | ---: | ---: | ---: | ---: | ---: |
| Frequência no T1 | 2 | 37 | 576 | 12 | 525 |
| Coocorrências adjacentes | 12 | 53 | 576 | 15 | 496 |
| Escolha perfeita até quatro, sem propostas inúteis | 39 | 247 | 286 | 0 | 0 |

A seleção adjacente pediria **7 615 807 488 B** de ranges alinhados, dos quais **6 558 056 448 B** não teriam uso na camada/tile prevista. As 65 primeiras leituras certas representam 859 248 000 B úteis. O teto de quatro buffers representa 52 887 552 B, além das tabelas, contabilidade e cópias. Mesmo concedendo cada um dos 65 acertos grátis, servir os 310 restantes a 8 GB/s tomaria 512,244 ms quando cabem 90,641 ms. O custo real do tráfego falhado e da contenção aumentaria o défice. Esses bytes são trabalho proposto em replay; o portátil não os transferiu nesta experiência.

**NO_GO para cumprir o alvo nominal apenas com esta regra e os custos exteriores fixos.** Mesmo conhecendo o futuro, os quatro lugares só poderiam cobrir 286; a 8 GB/s seriam necessários 321 e a 4,5 GB/s seriam necessários 345. O oráculo obtém 39/40 na primeira chamada apesar de lhe faltar um antecessor para a camada zero, e 247/335 na segunda. É um teto por largura que concede tempo ilimitado para as quatro leituras. O limite independente por duração dos intervalos usa a mesma agenda. [Janelas reais de antecipação](../tier_budget/first_use/previous_layer/README.md)

Há uma observação positiva para combinações: com a mesma quantidade pedida, a política adjacente cobre **26** primeiras leituras a mais que a frequência. O número 65 coincide com o total coberto pelo banco histórico last353; a identidade dos acertos decide quanto os métodos acrescentam um ao outro. O treino e a avaliação vêm de dois turnos encadeados da mesma conversa reproduzida em execuções independentes. O ganho em segundos e a generalização a outros pedidos permanecem por medir.

Duas execuções reabriram os raws da parte 63 e o original/arquivo da parte 97, em 0,86/0,82 s e até 86 496 KiB de RSS. Os recibos finais têm o mesmo SHA-256 `87fd5325baa876734e6406884df1252e3ce6c37e31744549896a651fdd09ae5d`. As duas primeiras exportações preservadas omitiram os campos de contagem zero apenas no total do oráculo. A representação final escreve esses dois zeros. Nenhuma campanha do modelo foi iniciada.

```sh
python3 -IB "$STUDY/test_score.py"
python3 -IB "$STUDY/score.py" --part63 "$ARCHIVE/part-63" \
  --family "$ARCHIVE/part-97/tesy-c281-pack-observer-natural-20261125-r01" \
  --new-output-dir "$NEW"
```
