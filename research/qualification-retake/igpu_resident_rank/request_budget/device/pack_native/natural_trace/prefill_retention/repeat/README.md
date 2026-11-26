# O mesmo ganho em bytes expõe tempos diferentes em duas execuções

**No novo pedido, mesmo oferecendo de graça todas as callbacks de remap CPU, ainda faltariam 1,206 s para os 10 s.** A margem no pedido P anterior era positiva, 90,641 ms. Ambos produziram as mesmas 7 012 linhas de quatro ranks, partiram dos mesmos 1 440 slots (incluindo gerações e claims) e tiveram as mesmas 375 primeiras leituras CPU nos mesmos sítios. O destino dos bytes é reproduzível; o tempo disponível para os servir mudou. [Pré-registo](protocol.md) · [Duas agendas e quatro braços por preço](receipt.json)

| Segundo turno com journal | P, parte 97 | P com T1 completo, parte 106 |
| --- | ---: | ---: |
| Primeiro conteúdo final medido | 18,325561 s | 19,528568 s |
| Decode medido para 47 saídas | 8,946626 s | 9,213847 s |
| Tempo desde o retorno da call 46 até ao primeiro conteúdo final, limite superior | 3,665 ms | 3,595 ms |
| Soma dos 106 hiatos drenados da camada anterior | 768,379 ms | 841,913 ms |
| Orçamento para as callbacks CPU após cobrar o exterior do primeiro final | +90,641 ms | **−1 206,045 ms** |
| Orçamento para as callbacks CPU do decode após cobrar o seu exterior, a 6 tok/s | 3 618,919 ms | 3 308,780 ms |

### Banco de T1 e antecedência de uma camada

Os dois cenários seguintes usam a seleção causal da nova captura, confirmada antes do POST, perfis de 40 slots e predição perfeita, com 8 GB/s úteis e transferências parciais. Cada coluna usa apenas os prazos do respetivo processo. Os 101 acertos da política de frequência cobrem o mesmo conjunto de primeiras leituras. O piso de serviço é 95,035 ms no P97 e 79,140 ms no novo P. O primeiro já excede a margem de 90,641 ms. No novo P o próprio exterior já excede o alvo. A diferença medida entre dois pedidos isolados não determina uma distribuição de latências. Estes resultados fecham a suficiência desta composição sob os custos exteriores observados. O efeito da política completa sobre a velocidade exige implementação.

Até a escolha retrospetiva perfeita entre as vítimas de todo T1, limitada a 353 lugares, precisaria de 1,915/1,521 ms nas callbacks. O seu sinal perante os 10 s **muda de favorável no P97 para desfavorável no novo P**. Em ambas as execuções, toda a preparação da cache, coordenação, entrega, proteção do decode e serviço dos restantes misses CPU estão concedidos gratuitamente. Para o pedido novo, a melhoria tem de atuar também fora destes remaps. [Comparação das duas políticas e bytes de captura](../README.md)

### O que entrou no relógio do cliente

O relógio congelado começa antes da entrada na função de streaming. No ON da parte 106, o cliente selou (T1) e a escolha do banco **antes do POST de T2**, mas **dentro** desse relógio. A selagem ocupou **645,215 ms**. Todo o intervalo até à entrada na função de streaming foi 646,428 ms (1,217 ms no OFF). A diferença entre esses números localiza o custo de diagnóstico. Conceder grátis até os 646,428 ms inteiros, além de todos os remaps CPU, ainda deixaria **559,617 ms** acima de 10 s. Este crédito foi calculado após a observação como sensibilidade adicional. O tempo oficial do ON continua a ser 19,529 s. Uma política real teria de pagar o trabalho que executasse entre pedidos. [Timestamps reabertos](client.json) · [Verificador do intervalo](client_interval.py)

Duas aplicações independentes ao original e ao arquivo produziram o mesmo SHA-256 `3d52e5abce57d286c41edc6533756db5ef55e564bcc5a76620ae4cec5213447f`, até 2 s por processo e menos de 75 MiB de RSS. A decomposição adicional produziu `4f06a3fa7e9f290abc18e43de89fd0692bffe7147046ebd95fd0a5cfc729d471`. Estes comandos reabrem os journals já medidos, sem executar o modelo.

```sh
python3 -IB "$REPEAT/score.py" --session "$FULL_SESSION" --session-sha256 "$FAMILY_SHA" \
  --p97 "$P97" --new-output-dir "$NEW"
python3 -IB "$REPEAT/client_interval.py" --session "$FULL_SESSION" --session-sha256 "$FAMILY_SHA" \
  --repeat "$NEW/receipt.json" --repeat-sha256 "$REPEAT_SHA" --new-output-dir "$CUT_NEW"
```
