# Quanto resta por ganhar numa conversa com 40 slots?

**GO para estudar outra política causal de substituição.** Desde a cache P realmente obtida pelo prefixo C294 até ao fim dos 32 passos de decode, a melhor escolha com conhecimento do futuro requer 1 336 cargas nominais ou 2 172 em código, incluindo o conjunto F de R0. São 37,10% e 36,38% menos cargas que o R0 observado. O limiar de 10% é ultrapassado nas réplicas 2 e 3 de cada caso. Trata-se de um ótimo offline de um problema com restrições relaxadas. A estratégia de frequência causal já testada nesse intervalo aumentou as cargas. [Protocolo](protocol.md) · [Recibo dos quatro braços](evidence/receipt.json) · [Contraprova causal](../prefill_causal_continue/README.md)

| C294 | R0 incremento + 32 passos | Distintos ausentes em P | Ótimo, F livre | Ótimo, conjunto F exigido | Poupança máxima em cargas |
|---|---:|---:|---:|---:|---:|
| Nominal, braços 2 e 3 | 2 124 | 1 208 | 1 335 | 1 336 | 788 |
| Código, braços 2 e 3 | 3 414 | 1 704 | 2 172 | 2 172 | 1 242 |

No nominal, o ótimo com F custa 904 cargas CPU e 432 CUDA. Em código custa 1 628 CPU e 544 CUDA. Cada carga tem 13 219 200 B de payload original. Fixámos P por posição e verificámos as 4 608 procuras de decode de cada conversa. No problema de residência, cada conjunto da wave tem de caber simultaneamente nos slots da camada. Acrescentar os residentes de F como último conjunto faz pagar as faltas necessárias ao estado terminal. A permutação física dos slots, cópias, gerações, parking e contenção continuam por cobrar. Os números minimizam a soma de incremento e decode; não identificam o custo de cada fase numa realização nem um ganho de parede.

Uma hipótese para a próxima janela é dar baixa prioridade inicial às entradas novas e promover as que voltam a ser usadas, com a regra estática SRRIP. Jaleel et al. estudaram caches de hardware e sequências com muitos dados lidos uma vez. A transferência a verificar aqui é a seleção da vítima de um expert, com pins simultâneos por wave, dois tiers e 40 slots por camada. O primeiro teste deve fixar a inicialização e desempate antes de observar os resultados, confrontar R0 e uma ablação de recência nas duas conversas, cobrar o estado de entrada e de retorno e proteger incremento e decode separadamente. A vantagem sobre LRU e a latência do pedido permanecem desconhecidas. [Jaleel et al., ISCA 2010, fonte dos autores](https://jaleels.org/ajaleel/publications/isca2010-rrip.pdf)

Pré-registo c55fa5c8. Código em e60b83250be196966407dbd4da8e7e69a8ee1c2c. As duas execuções em árvore limpa terminaram em 0,54 s cada com até 81 184 KiB de RSS. Geraram o mesmo SHA-256 d2f0912118512131cc6c5719947bb44b1bc1d651e21a7b5d0199eac84026b0cf. Três testes sintéticos. Sem pesos, GPU ou forwards.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 120 prlimit --as=805306368 -- \
  python3 -B research/qualification-retake/prefill_interval40/screen.py \
  --family "$WRT40" --historical-results "$C7/results" --new-output-dir "$NEW_OUT"
```
