# A popularidade disponível no fim do prefixo

**NO_GO da política top 40 por `route_hotness` no regime C294.** Mesmo que os 40 experts escolhidos por camada estivessem gratuitamente disponíveis no início do decode e todas as substituições posteriores fossem ótimas, seriam precisas 1 106 cargas no nominal e 1 179 em código. A projeção admite até 504 cargas em 32 tokens para atingir 6 tok/s, a 10 Gbit/s dedicados aos pesos e 13 219 200 B por carga. O ranking só encontrou contadores positivos na camada 35. O desempate pelo ID do expert decidiu mais de 99% das 1 440 escolhas. [Protocolo prospetivo](causal_prefix_protocol.md) · [Recibo por braço](causal_prefix_evidence_r2/receipt.json)

| Braço | Pares camada/expert em `seen` | Contadores positivos | Escolhidos com contador zero | Ausentes da cache no fim do prefixo / início real do decode | Cargas mínimas posteriores | Limite superior, tok/s |
|---|---:|---:|---:|---:|---:|---:|
| nominal 2 ON | 2 659 | 10 | 1 430 | 985 / 983 | 1 106 | 2,736 |
| nominal 3 ON | 2 659 | 10 | 1 430 | 985 / 983 | 1 106 | 2,736 |
| código 2 ON | 2 476 | 8 | 1 432 | 984 / 991 | 1 179 | 2,566 |
| código 3 ON | 2 476 | 8 | 1 432 | 984 / 991 | 1 179 | 2,566 |

No pin C294 `237e3b8789650fd68b97641c5b8e259d198ed3b1`, `src/llama-graph.cpp` seleciona a função de remap pelo número de waves. Em `src/llama-moe-stream.cpp`, só `llama_moe_stream_remap` incrementa `route_hotness`, uma vez por expert distinto na ubatch. Os valores persistem entre chamadas, são saturados e podem ser reduzidos a metade quando o contador global de chamadas passa pelo teste de decaimento dentro desse remap. O intervalo é 64 vezes o número de camadas streamed. A via de várias waves invoca `plan_waves_locked`; reconstrói `touched` e `uniq` e incrementa o número global de chamadas sem atualizar a popularidade. Assim, o vetor de 128 valores por camada está disponível antes da chamada incremental, com cobertura limitada pelas operações que o alimentam. O ficheiro de implementação corresponde ao SHA-256 congelado `270ede951c3911c8acbd878600f7bab3692215b820d5853d67071b790297f9fc`. [Identidade do backend e ficheiros pinados](../../results/c294-feature-ready-service-window-20261006/protocol.json)

`seen[e]` passa a 1 quando o serviço reserva um slot para o expert pela primeira vez. Conta também reservas de antecipação e conserva o bit depois de uma expulsão. `slot_last_use` pertence aos 40 slots físicos de cada camada e recebe um novo carimbo na reserva e no uso. A identidade expulsa perde a sua associação ao carimbo desse slot. Em cada repetição, a política selecionou 584 pares camada/expert nunca antes reservados no nominal e 646 em código. Na camada 35, o nominal teve 118 experts empatados a zero para as últimas 30 escolhas e o código teve 120 para as últimas 32. Nas restantes 35 camadas, os 128 experts empataram a zero para 40 lugares. [Snapshot de origem](../../tools/block_native_run.cpp) · [Fronteira reconstruída do decode](cache_boundary.md)

A seleção lê somente os contadores após o prefixo. Depois de fixar os conjuntos, o avaliador usa as rotas observadas no decode para conceder substituição ótima e quantificar um limite favorável. O payload posterior perfaz 14 620 435 200 B no nominal e 15 585 436 800 B em código. A preparação real também teria de materializar os experts ausentes, gerir vítimas e preservar ou reconstruir o estado ao longo de `prefill153`. O teste concedeu todo esse trabalho gratuitamente. A conclusão diz respeito a estes contadores, desempate e cargas C294. Uma série completa de frequências do router em prefill multi-wave exigiria outra observação e outro protocolo. [Cálculo](causal_prefix.py) · [Solver e hipóteses de banda](cache_bound.py)

A execução consumiu 0,887 s, com máximo observado de 103 596 KiB de RSS e zero forwards. Dois arranques anteriores falharam ao mapear a dependência NumPy porque o limite fora aplicado a todo o espaço de endereçamento virtual. Ambos terminaram durante a importação, antes de ler qualquer score, criar uma saída ou executar a política. Na execução admitida, o orçamento de memória incidiu sobre RSS, observado a cada 5 ms, com interrupção aos 256 MiB ou 60 s. A comparação de quatro braços produziu o recibo `eb4d382cf512612372dcd0d892ec8681c1f00e5896f25d57da717c419818a543`. O artefacto contém apenas digests e contagens agregadas.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B \
  research/qualification-retake/causal_prefix.py \
  --raw-dir "$TESY_C294_RAW" --new-output-dir "$TESY_NEW_PREFIX_OUT"
```
