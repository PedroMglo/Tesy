# O ganho do pack sobrevive à troca de ordem?

**MEDIDO no portátil.** O primeiro conteúdo final chegou mais cedo com o pack nas duas ordens. R usa o servidor Tesy C281 com a biblioteca C269 de referência. O e P usam C291, com as três matrizes do expert juntas no pack apenas em P. Nos dois blocos os pesos vieram do NVMe interno e o cliente enviou T1/T2 ao mesmo servidor local. Cada contraste O/P compara a mesma biblioteca e o mesmo trabalho natural. [Critério congelado](order.md) · [Primeiro bloco, relógios e falhas](README.md)

**GO para conservar o pack como componente da próxima combinação. NO_GO para o pack isolado como solução M4.** No segundo turno o ganho O/P no primeiro conteúdo final foi 2,900 s em R/O/P e 2,002 s em P/O/R. São 13,54% e 9,85% do tempo de O. O ganho de prefill foi 1,571 e 0,879 s, o de decode 1,360 e 1,141 s. O primeiro turno também beneficiou nas duas ordens. A melhor observação P juntou **18,313 s** ao primeiro final, **18,565 s** à validação e **5,361 tok/s** no mesmo pedido. Faltaram 8,313 s e 0,639 tok/s aos alvos. M3 PARTIAL, M4 NOT_MET. [Dados dos dois blocos](evidence/ordens.json)

| Ordem | Turno | Braço | Primeiro final (s) | Transporte (s) | Válido (s) | Prefill (s) | Decode (s) | tok/s | Exterior até ao fim do transporte (ms) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| ROP | T1 | R | 84,354 | 84,806 | 84,808 | 64,365 | 20,429 | 3,818 | 10,967 |
| ROP | T1 | O | 84,477 | 84,921 | 84,924 | 64,425 | 20,485 | 3,808 | 10,877 |
| ROP | T1 | P | 78,412 | 78,795 | 78,797 | 60,846 | 17,938 | 4,348 | 10,349 |
| ROP | T2 | R | 21,054 | 21,351 | 21,355 | 11,023 | 10,317 | 4,555 | 10,327 |
| ROP | T2 | O | 21,414 | 21,699 | 21,701 | 11,393 | 10,291 | 4,567 | 14,614 |
| ROP | T2 | P | 18,515 | 18,763 | 18,766 | 9,822 | 8,930 | 5,263 | 10,605 |
| POR | T1 | P | 74,658 | 75,022 | 75,024 | 57,533 | 17,478 | 4,463 | 10,324 |
| POR | T1 | O | 81,084 | 81,514 | 81,516 | 61,697 | 19,806 | 3,938 | 10,970 |
| POR | T1 | R | 81,193 | 81,618 | 81,621 | 61,791 | 19,817 | 3,936 | 11,061 |
| POR | T2 | P | 18,313 | 18,563 | 18,565 | 9,784 | 8,768 | 5,361 | 11,156 |
| POR | T2 | O | 20,315 | 20,583 | 20,585 | 10,663 | 9,908 | 4,744 | 11,983 |
| POR | T2 | R | 20,413 | 20,681 | 20,683 | 10,748 | 9,921 | 4,738 | 11,863 |

T1 processou 2 043 posições e gerou 78 IDs. T2 recuperou 2 044 posições de histórico, acrescentou 153 e gerou 47 IDs, incluindo EOG. Todos os seis servidores passaram ambos os validadores e a verificação das sequências, dos 71/40 frames e da identidade das bibliotecas e descritores. [Revisor e verificações de ordem](order_review.py)

| Contraste e turno | Primeiro final (s), ROP / POR | Válido (s), ROP / POR | Prefill (s), ROP / POR | Decode (s), ROP / POR | tok/s, ROP / POR |
|---|---:|---:|---:|---:|---:|
| R→O T1 | -0,122 / 0,109 | -0,115 / 0,105 | -0,059 / 0,094 | -0,056 / 0,011 | -0,010 / 0,002 |
| R→O T2 | -0,360 / 0,098 | -0,346 / 0,098 | -0,370 / 0,085 | 0,026 / 0,012 | 0,012 / 0,006 |
| O→P T1 | 6,065 / 6,426 | 6,127 / 6,492 | 3,578 / 4,164 | 2,547 / 2,327 | 0,541 / 0,524 |
| O→P T2 | 2,900 / 2,002 | 2,936 / 2,020 | 1,571 / 0,879 | 1,360 / 1,141 | 0,696 / 0,617 |
| R→P T1 | 5,942 / 6,535 | 6,011 / 6,597 | 3,519 / 4,258 | 2,491 / 2,338 | 0,530 / 0,527 |
| R→P T2 | 2,540 / 2,100 | 2,589 / 2,118 | 1,202 / 0,964 | 1,387 / 1,153 | 0,707 / 0,623 |

Em segundos, o sinal positivo indica tempo poupado. Em tok/s indica maior débito do braço de destino. O permaneceu na segunda posição. P passou de último a primeiro e R fez a troca inversa. São duas observações por braço num mesmo portátil, com o estado natural das caches do sistema. O efeito em código a trabalho fornecido e o contexto/sustentação têm avaliadores próprios. [Custos e âmbito C293](../product-protocol.md)

| Ordem e braço | READY (s) | Limpeza (s) | RSS / cgroup (GiB) | VRAM (MiB) | CPU / GPU / NVMe (°C) | GPU (J estimados) | Cobertura do monitor (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| ROP R | 4,129 | 1,026 | 14,86 / 15,10 | 6848 | 83,5 / 58,6 / 52,9 | 1497,9 | 110,6 |
| ROP O | 3,900 | 0,869 | 14,91 / 14,73 | 6848 | 83,5 / 58,4 / 53,9 | 1531,6 | 110,6 |
| ROP P | 4,016 | 1,258 | 14,91 / 14,72 | 6848 | 83,5 / 58,7 / 54,9 | 1445,0 | 101,7 |
| POR P | 4,040 | 0,769 | 14,91 / 14,71 | 6848 | 83,5 / 57,8 / 50,9 | 1320,6 | 97,5 |
| POR O | 3,834 | 0,948 | 14,91 / 14,91 | 6848 | 83,5 / 56,6 / 51,9 | 1419,9 | 105,9 |
| POR R | 3,857 | 1,181 | 14,86 / 14,67 | 6848 | 83,5 / 58,7 / 52,9 | 1450,8 | 106,5 |

Os seis processos saíram com código zero e zero swap. O limite foi 20 GiB, com paragem a 19,5 GiB e C118 antes de cada lançamento. A limpeza decorre entre o último corte do cliente e a verificação da saída do processo, da porta e do scope. A energia da GPU provém da integração das amostras; a energia do portátil permanece desconhecida. As duas famílias demoraram 631,518 s e 620,522 s. As esperas TCP ficaram fora dos pedidos. A execução R01 interrompida acrescentou um servidor e dois pedidos anteriores aos seis processos e doze pedidos completos desta comparação. [Manifestos e reprodução](reproduzir.md)
