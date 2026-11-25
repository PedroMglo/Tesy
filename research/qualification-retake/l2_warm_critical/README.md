# Quanto tempo pode valer uma L2 preparada durante o histórico?

**GO apenas para testar capacidade finita com 378 entradas preparadas em P.** À escala de serviço 1,0 do C295, uma escolha offline de experts já roteados no prefixo deixa 102–194 ms de folga nos quatro braços para completar 32 passos em 5,333 s. Com 243 entradas, até a escolha arbitrária falha nos dois braços nominais. À escala 1,2, a escolha arbitrária de 378 entradas também falha no nominal. São limites condicionais de decode no C294 com trabalho fornecido. A qualificação natural de produto continua em M3 PARTIAL e M4 NOT_MET. [Protocolo](protocol.md)

### Duração dos 32 passos por braço

Cada célula dá segundos nas escalas de serviço **0,8 / 1,0 / 1,2**. Em K=0, os três universos coincidem. As duas réplicas conservam as suas próprias durações de leitura e cópia.

| Entradas em P | Universo de escolha | nominal153-2 | nominal153-3 | code153-2 | code153-3 |
|---:|---|---:|---:|---:|---:|
| 0 | Sem cópias iniciais | 6,857 / 8,128 / 9,399 | 6,902 / 8,170 / 9,437 | 6,266 / 7,379 / 8,491 | 6,270 / 7,381 / 8,491 |
| 243 | Qualquer chave | 4,917 / 5,703 / 6,489 | 4,981 / 5,768 / 6,556 | 4,193 / 4,787 / 5,381 | 4,234 / 4,836 / 5,437 |
| 243 | Roteadas no prefixo | 5,091 / 5,921 / 6,750 | 5,152 / 5,982 / 6,812 | 4,533 / 5,212 / 5,890 | 4,555 / 5,236 / 5,918 |
| 243 | Residentes físicos em P | 5,512 / 6,447 / 7,382 | 5,594 / 6,535 / 7,476 | 5,140 / 5,971 / 6,802 | 5,138 / 5,965 / 6,793 |
| 378 | Qualquer chave | 4,170 / 4,769 / 5,368 | 4,239 / 4,841 / 5,443 | 3,462 / 3,873 / 4,284 | 3,494 / 3,910 / 4,326 |
| 378 | Roteadas no prefixo | 4,491 / 5,170 / 5,850 | 4,552 / 5,232 / 5,912 | 4,475 / 5,140 / 5,804 | 4,489 / 5,154 / 5,819 |
| 378 | Residentes físicos em P | 5,512 / 6,447 / 7,382 | 5,594 / 6,535 / 7,476 | 5,140 / 5,971 / 6,802 | 5,138 / 5,965 / 6,793 |

A comparação mantém os quatro workers, routing, 1 152 grupos de posição e camada, cópias para o primário, publicação e trabalho fora das barreiras. O cenário concede uma segunda cache ilimitada após P. Uma leitura repetida após a publicação da mesma chave pode ser eliminada gratuitamente. As cópias em P só alteram o decode quando a primeira requisição posterior àquela fronteira já ocorre no decode. Para cada grupo com até quatro serviços, o otimizador enumera os subconjuntos e recalcula o máximo das durações restantes. A programação dinâmica escolhe os grupos dentro da capacidade global. O replay dos workers confirmou os testemunhos nas três escalas de cada braço. [Otimizador e prova](optimizer.py) · [Doze controlos C295 e cenário com P vazio](../l2_critical/README.md)

### Bytes necessários antes do pedido

Para a escolha das chaves roteadas no prefixo com K=378, cada admissão representa 13 219 200 B de payload codificado. A última coluna dá o custo adicional máximo **no relógio do decode** à escala 1,0 para manter a meta. A preparação anterior ao pedido tem o seu próprio custo.

| Braço | Cópias iniciais | Origem CPU (B) | Origem CUDA (B) | Escrita em RAM (B) | Folga (ms) |
|---|---:|---:|---:|---:|---:|
| nominal153-2 | 378 | 3 701 376 000 | 1 295 481 600 | 4 996 857 600 | 163,117 |
| nominal153-3 | 378 | 3 701 376 000 | 1 295 481 600 | 4 996 857 600 | 101,659 |
| code153-2 | 270 | 2 392 675 200 | 1 176 508 800 | 3 569 184 000 | 193,610 |
| code153-3 | 277 | 2 419 113 600 | 1 242 604 800 | 3 661 718 400 | 179,400 |

Com 243 chaves, preencher a L2 em P requer 3 212 265 600 B. Capturar as leituras durante o histórico exige preservar estes bytes em RAM até P e debitar a sua movimentação. Se o operador partir dos slots existentes em P, os residentes CUDA exigem uma cópia GPU→host quando já não existe cópia codificada no host. Neste universo, ambas as capacidades chegam ao mesmo ótimo e o caso nominal falha mesmo à escala 0,8. O universo arbitrário concede os bytes mesmo quando a sua origem anterior é desconhecida. O WRT1 documenta aquisições orientadas pelo routing, mas a escolha das que valeria reter depende das consultas futuras desta fixture. [Estados, chaves escolhidas, hits, bytes por tier e tempos por braço](evidence/receipt.json)

O teste seguinte deve cobrar as entradas que persistem até I, a ocupação máxima ao longo do incremento e dos 32 passos e as cópias das entradas efetivamente usadas para staging. Em particular, beneficiar de todas as repetições depois de P pode exigir mais RAM que a reservada. Uma eventual política causal precisará ainda de escolher as entradas durante o histórico e de demonstrar os custos de cópia e coordenação no portátil. [Protocolo da residência finita em I](../l2_decode_entry/protocol.md)

### Reprodução

O protocolo foi congelado em `89388df4`. As duas execuções sem modelo usaram a checkout limpa `bf2fa7e4301b1097e6f5e965ce85fc0fa0e90ed7`, árvore `985dcfb18250fa759b319bbf6ad00a4fdad72d85`. A saída r01 demorou 3,15 s e atingiu 108 368 KiB RSS. A r02 demorou 3,16 s e atingiu 107 944 KiB. As duas produziram o recibo SHA-256 `7c51a5606505c8353971adec1beda99450215d4fab69b6dd9566523d09c7157e`. Zero forwards e zero GPU. [Verificador](screen.py) · [Recibo](evidence/receipt.json)
