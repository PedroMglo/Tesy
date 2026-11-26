# Custo do atalho na tile real de prefill CPU0

**MEDIDO no Ryzen AI 9 HX 370.** Na tile C266 de 32 posições, o atalho para as sete waves vazias reduziu a mediana do FFN completo de **17,566 para 14,622 ms** e de **17,413 para 14,632 ms** nos dois pares em ordem inversa. As poupanças foram **16,76% e 15,97%**. O FFN calculou os mesmos 92 160 valores F32 finitos bit a bit, com as mesmas rotas, máscaras e os mesmos 40 slots que o controlo. **GO para ensaiar a fronteira entre router e FFN.** No menor dos pares, a seleção e sincronização adicionais que uma integração real exija têm menos de **2,895 ms por esta tile** antes de esgotar o ganho incluindo a construção. [Protocolo anterior ao ensaio](protocol.md) · [Todos os tempos individuais](result.json)

| Processo por ordem de execução | Nós do grafo / MMID | Construção e alocação | Parede residente, mediana | Mínimo–máximo das 7 execuções |
|---|---:|---:|---:|---:|
| 1 · OFF | 110 / 24 | 0,283 ms | 17,566 ms | 17,032–17,831 ms |
| 2 · ON | 47 / 3 | 0,240 ms | 14,622 ms | 14,481–15,046 ms |
| 3 · ON | 47 / 3 | 0,252 ms | 14,632 ms | 14,594–15,677 ms |
| 4 · OFF | 110 / 24 | 0,366 ms | 17,413 ms | 17,270–17,842 ms |

A parede inclui publicar as entradas, executar e sincronizar o FFN completo. O revisor somou uma construção, desde a seleção pós-router até à alocação, à mediana de cada braço. O ganho passou então a 2,987 e 2,895 ms, respetivamente. O custo de se obter esta fronteira dentro de uma chamada real ainda não foi medido. Os quatro processos da tabela constituem dois pares. As sete observações residentes de cada processo partilham estado e não suportam inferência sobre a distribuição das latências da conversa.

**Exatidão.** Antes do timing, STOCK, OFF e ON executaram o router CPU0 na geometria original de 153 posições e compararam com C266 os logits pré e pós-bias, top-4 e pesos. Os cinco experts foram escolhidos pelo target nas posições 32–63. OFF e ON são modos do mesmo ELF. O grafo de OFF tem a mesma assinatura estrutural do executável independente STOCK. ON manteve o serviço e a máscara das oito waves, incluiu as três projeções originais na wave ativa e especializou a acumulação das sete completamente estacionadas. A ordem entre ranks ficou preservada. O revisor independente reconstruiu 1 024 IDs físicos e 1 024 máscaras a partir dos IDs oficiais e do estado dos slots. Em cada um dos sete processos confrontou os bytes finais do FFN com a fatia da captura C266. [Referência numérica do operador](../README.md) · [Operação no grafo](tail.h) · [Revisor da camada](review.py)

**Residência e recursos.** Cada processo frio original devolveu 66 109 440 B em cinco leituras no FD do pack parcial e enviou 66 096 000 B nos 15 SET. As passagens residentes deram cinco hits e zero novas leituras ou SET. Os quatro workers escoaram e fizeram join. Os donos, gerações, estados e claims dos 40 slots coincidiram entre processos. A família de exatidão demorou 533 ms e a família de timing 998 ms, com picos respetivos de 161,2 e 162,9 MiB e zero swap nas unidades. As 56 observações de supervisão dos builds e famílias registaram como máximos 65,125 °C na CPU, 42,37 °C na RTX e 32,85 °C no NVMe. Sem processos de cálculo na GPU. O ensaio usou as fatias locais já verificadas da camada, sem abrir o GGUF integral ou executar pedidos de conversa. A energia por operação continua desconhecida.

O primeiro build passou e a tentativa de exatidão R01 parou antes de executar STOCK, por falta do bit de execução no arquivo. R02 usou uma cópia de trabalho com o mesmo SHA. O arquivo conserva a saída vazia e a falha. O commit do ensaio qualificado é `7c8bacaee3902403441ad01be3a1bb825ea7b7b4`, o ELF candidato tem SHA `661be1057c7ca88dddcfbce80a65b3fba6018c94bc123d910da7e2eec09547f3`. O revisor produziu o mesmo compacto nos originais e na cópia selada, SHA `5c64bb62b9ca9a4be2b1ab2e3cb41cff30aee848543bd2d39a30e55585a622a9`. [Falha preservada](r02.md) · [Recibo de 60 ficheiros, 5 517 347 B](../../../../../../../../../../../../../../private_archive/part-201.json)

**Condição para avançar.** A fixture dispõe da saída exata do router ao construir o grafo. Numa conversa, o backend precisa dessa informação a tempo e do percurso original para waves parcialmente ativas. O próximo teste compara despacho após o router com o grafo monolítico, incluindo a espera, a seleção e a execução. Deve cobrir uma e várias waves ativas, máscaras mistas, os mesmos pesos e o estado do manager. Os 16% desta tile não constituem uma estimativa para todo o prefill nem para o decode. O valor de produto continua a ser medido no pedido natural com histórico real. [Intervalos das 739 waves no nominal](../../empty.md)

Para reabrir sem carregar o modelo, usar a pasta preparada de C266 com SHA `a3a6028b45719ee0a1c63f689a2e6896b5a401ee394d5aa9d3188d98e72dc269`. A preparação, fontes, ordem dos sete processos, limites e recibos de build são verificados pelos programas.

```sh
python3 -IB "$STUDY/review.py" --root "$AR/part-201" --input "$C266" --new-output-dir "$NEW"
```
