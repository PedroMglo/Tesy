# Mudar a vítima sem mudar a geometria numérica

**INCONCLUSIVE para a latência.** Um oracle offline de capacidade consegue terminar com a distribuição física inicial do primeiro decode depois de 683 cargas CPU e 356 CUDA na chamada de 148. O registo original tem 761 e 416. Para chegar a esse estado o oracle paga ainda 219 e 116 cópias locais de um expert. As políticas LRU causais nas duas ordens iniciais testadas aumentam as admissões em ambos os tiers. A experiência testa o custo de recuperar a cache que o produto vai utilizar no retorno. [Código](oracle.py) · [Recibo das 36 camadas](victim-evidence/receipt.json) · [Definição das duas ordens](lru-protocol.md)

**Estado inicial.** Cada reserva inicia uma versão da slot e cada vítima READY ou hit identifica o residente de uma versão. Com os eventos só da chamada, há testemunhas para 878/1000 slots CPU e 351/440 CUDA na entrada e na saída. Usando o primeiro/último testemunho válido no intervalo da mesma versão em toda a captura, obtêm-se 986/1000 e 438/440. As 14+2 restantes atravessam a chamada sem escrita. O construtor físico mantém-nas nas posições originais. A ordem por token, a hotness, a fila e os relógios de uso iniciais continuam desconhecidos. A política recebe a máscara de slots incógnitas como premissa da simulação.

| Demanda satisfeita com 40 slots/camada | CPU | CUDA |
|---|---:|---:|
| Histórico, call 148 | 761 | 416 |
| Belady batched, só sets da wave corrente, retorno livre | 563 | 291 |
| Acrescentar conjunto lógico final | 583 | 318 |
| Incluir preload da wave seguinte, parking, incógnitas protegidas e conjunto final | 623 | 332 |
| Atribuição física construída, incluindo a releitura para desfazer os ciclos de permutação | **683** | **356** |
| Cópias adicionais no mesmo tier na última linha | **219** | **116** |

Em cada wave o controlador conhece os IDs que o target já calculou para aquele tile. Na projeção alargada residem toda a wave, o preload dentro do mesmo tile e os IDs de parking deduzidos da ordem lógica anterior. Belady escolhe fora do conjunto protegido o residente cuja próxima utilização está mais longe. Trocar uma vítima escolhida por uma de próximo uso mais tardio preserva as necessidades correntes e não antecipa a próxima falta. A fixture compara o custo ótimo com enumeração exaustiva em 2 592 sequências/estados pequenos. Nas projeções sem restrição sobre as incógnitas, o oracle recebe a capacidade total. O resultado vale para o contrato de conjuntos escolhido. As primeiras admissões e as que o histórico perdeu por outra escolha de vítima entram nas contagens. O denominador difere das 184 recargas específicas.

A realização com mapa final preserva a posição de destino nos empates e repõe o conjunto final com 39 cargas CPU e 32 CUDA, já incluídas em 623/332. Restam 60 e 24 ciclos em 279 e 140 slots. Em cada ciclo descarta-se um residente, copia-se cada um dos restantes para o seu local e recarrega-se o primeiro do GGUF. O construtor compara todas as slots, incluindo as incógnitas, após o último movimento. Usa zero slots de scratch adicionais, cada cópia movimenta 13 219 200 B de payload e os cruzamentos CPU↔CUDA dependem das cargas originais do tier. Esta realização é uma testemunha. Vítimas ou desempates diferentes poderão ter outra despesa. As reservas por geração, bytes físicos, custos das novas faltas, estado do controlador e paridade do primeiro decode continuam sem prova nesta alternativa.

| LRU com reposição física, slots desconhecidos protegidos | Cargas CPU | Cargas CUDA | Cópias CPU | Cópias CUDA |
|---|---:|---:|---:|---:|
| Slot de índice menor inicialmente mais antiga | 937 | 458 | 540 | 271 |
| Slot de índice maior inicialmente mais antiga | 929 | 466 | 527 | 265 |

O LRU toca os IDs da wave por ordem crescente e escolhe a vítima mais antiga entre os residentes elegíveis. O mapa futuro só participa na fase de reposição. As duas ordens iniciais hipotéticas expõem a sensibilidade à recência ausente. Ambas falham a redução de leituras cobradas. A decisão cobre estas duas hipóteses sobre o estado inicial. [Protocolo do controlo LRU](lru-protocol.md)

A distinção causal importante é entre a rota já calculada da wave atual e as rotas dos tiles futuros. No R0, a seleção de vítima ignora slots `keep` e em carga. O remap vai marcando os residentes da wave atual à medida que visita os IDs. Assim, um residente necessário ainda nesta wave pode ser expulso por uma procura anterior. Preproteger este conjunto é causal. Os resultados C164 com 44 slots e C286 com política de hotness de E já rejeitaram outras intervenções. As métricas e baselines dessas campanhas continuam nos respetivos relatórios. [C164](../C164-REPLAY-AND-POLICY-DECISION-20260930.md) · [C286](../C286-LOGICAL-ROUTE-POLICY-COST-NO-GO-20261006.md)

Reprodução, indicando um diretório novo:

```sh
python3 research/prefill-slot-proof/oracle.py --trace "$TESY_C135_TRACE" --new-output-dir "$NOVO_DESTINO"
```
