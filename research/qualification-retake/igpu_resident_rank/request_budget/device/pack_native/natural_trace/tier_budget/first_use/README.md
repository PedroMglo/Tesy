# As primeiras procuras CPU excedem os 90,641 ms

**NO_GO para atingir conjuntamente os alvos apenas retirando custo das callbacks CPU, se os mesmos pesos tiverem de chegar do NVMe depois da primeira procura observada.** A análise anterior deixava 90,641339 ms de margem para o primeiro final, concedendo que todo o remap CPU antes da amostra 45 fosse gratuito. Desta vez conservamos o custo mínimo de servir apenas 375 primeiras procuras CPU durante o prefill. Todo o resto do remap CPU, incluindo as 44 avaliações de decode antes da primeira peça final, continua gratuito. [Limite dos dois relógios](../README.md) · [Recibo reproduzido](result.json)

A observação é a mesma conversa P com o pack no NVMe interno. Esta interseção é uma **inferência secundária**, posterior à medição. Entre as 567 primeiras procuras estritas em ambos os destinos, 375 pertencem a buffers CPU e 192 a CUDA0. As 375 repartem-se entre 40 na chamada de 5 e 335 na chamada de 148, em 21 e 89 callbacks respetivamente. Cada par camada/expert estava ausente no início. A primeira geração foi reservada e enfileirada pela procura na própria primeira wave ou uniwave, o worker leu o pack, fez três SET e publicou antes do retorno da callback. Estes 110 intervalos host são causalmente separados. O payload útil CPU totaliza 4 957 200 000 B; os preads alinhados pediram e devolveram 4 958 208 000 B. O preço abaixo concede o padding, os SET e a publicação gratuitamente. [Definição da primeira utilização](../../release/protocol.md) · [Método secundário](protocol.md)

| Premissa isolada | Piso do serviço CPU estrito | Quanto excede a margem | Experts inteiros que cabem |
| --- | ---: | ---: | ---: |
| 8 GB/s úteis agregados | 619,650 ms | 529,009 ms | 54 de 375 |
| 4,5 GB/s úteis agregados | 1 101,600 ms | 1 010,959 ms | 30 de 375 |
| READ observado, quatro workers | 2 036,796 ms | 1 946,154 ms | — |
| Metade do preço de cada READ, quatro workers | 1 018,398 ms | 927,756 ms | — |

Os limites de volume requerem que os bytes úteis atravessem a interface comum **dentro dos intervalos**. A concorrência dos workers não multiplica a banda agregada. A 8 GB/s é preciso retirar da interface ou antecipar pelo menos 4 232 069 288 B nestas callbacks. Se a unidade de antecipação for o expert completo, isso requer **321 de 375**. A 4,5 GB/s seriam 4 549 313 975 B ou **345 experts inteiros**. O limite em bytes também vale para entregas parciais. Em alternativa, a poupança necessária pode ocorrer fora desta família CPU ou a partir de um estado inicial diferente, desde que a preparação, validade, tráfego e perdas sejam cobrados. Servir todos os bytes úteis no intervalo pediria pelo menos **54,690 GB/s**. O FD O_DIRECT e os retornos dos syscalls estão observados; a cobrança dessa circulação num desenho futuro é uma premissa explícita.

Os limites de duração são uma alternativa à cobrança por GB/s. O verificador soma, para cada callback, o máximo entre a maior duração de READ e um quarto do worker-tempo READ. Todos os jobs têm release e deadline dentro dessa callback. Se as durações diminuírem uniformemente, só 4,45% do piso observado caberia no intervalo. Esta análise não mediu um runtime novo, não soma os pisos de bytes e duração e não atribui os 375 serviços ao relógio de decode. O défice no primeiro final basta para fechar os dois alvos em conjunto, nestas condições.

A mesma cadeia de inputs e o mesmo executor `c1dd5ba2` produziram o resultado duas vezes, nos originais e na cópia privada verificada da parte 97, SHA-256 `cbbba4262589e1c55aa1f57393f207384dc42c3ddea7a2bd5c299ef5d79fa01e`. O programa reabre a auditoria de filas, as projeções de IDs, a atribuição de destino do pedido e o recibo das 567 primeiras procuras. Mantém os 47 tokens confirmados e o mesmo validador. Não houve inferência durante esta reanálise.

```sh
python3 -IB score.py --family "$FAMILY_P" --backend "$C291_SOURCE" --new-output-dir "$NEW_AUDIT"
python3 -IB -m unittest discover -s .
```
