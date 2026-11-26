# Popularidade C286 transferida para o decode C294

**NO_GO para o top-40 do contador causal C286 no USB observado.** Mesmo concedendo de graça a cache escolhida no começo do decode e reposição ótima com conhecimento do futuro, a regra excede as 504 leituras admissíveis em cada um dos quatro braços. Esta decisão fecha a regra transferida de popularidade com decaimento para estes inputs. A hipótese de selecionar por **frequência cumulativa sem decaimento** continua por medir. [Protocolo fixado antes da contagem](cross_prefix.md) · [Recibo](cross_prefix_evidence/receipt.json)

| Demanda C294 R0 | Snapshot E/C286 LOGICAL | Publicações R0 medidas | Mínimo com top-40 C286 | Bytes de payload | Teto a 10 Gbit/s | Leituras acima de 504 |
|---|---|---:|---:|---:|---:|---:|
| nominal153 ON2 | 2 | 1 081 | 846 | 11 183 443 200 | 3,577 passos/s | 342 |
| nominal153 ON3 | 2 | 1 081 | 846 | 11 183 443 200 | 3,577 passos/s | 342 |
| code153 ON2 | 6 | 1 308 | 1 193 | 15 770 505 600 | 2,536 passos/s | 689 |
| code153 ON3 | 6 | 1 308 | 1 193 | 15 770 505 600 | 2,536 passos/s | 689 |

**Origem do sinal.** O braço LOGICAL de C286 reinicializa o histórico. Por camada, para cada linha realmente consumida, contabiliza uma vez cada um dos quatro experts do router. A cada 64 linhas divide todos os contadores por dois, com arredondamento inteiro para baixo. Uma leitura repetida da mesma faixa do evento é idempotente. O prefixo é processado sob a política de substituição desse braço com `c262_layer_mode=0`. O cliente drena e grava `initial.json` antes de ativar o modo E para o incremento de 153. A entrada contém 2 044 e 1 952 IDs de prefixo, respetivamente, seguidos da mesma entrada incremental e dos mesmos 32 IDs fornecidos nos respetivos braços C294. Os dois protocolos identificam o mesmo GGUF, com SHA-256 `582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d` e 63 387 346 208 bytes. Os commits de backend são `a3dbfc977579af6edd253667502be2cbe2d8ec29` (C286) e `237e3b8789650fd68b97641c5b8e259d198ed3b1` (C294). C284 preservou a falha de qualificação original. A C285 qualificou fronteiras selecionadas numa fixture distinta. [Cliente C286](../../tools/logical_route_native.cpp) · [Protocolo C286](../../results/c286-logical-route-policy-cost-20261006/protocol.json) · [Protocolo C294](../../results/c294-feature-ready-service-window-20261006/protocol.json)

O ensaio usou o primeiro braço com o contador LOGICAL ativo por caso. Os contadores estavam positivos em pelo menos um expert de todas as 36 camadas de ambos os snapshots. As 36 tabelas de cada caso coincidem com as da repetição LOGICAL independente (nominal 2/3, código 6/7). O contador `route_hotness` da C294 R0, no screen de controlo, só tinha valores positivos numa camada. O top-40 C286 selecionou a pontuação zero em 135 das 1 440 entradas no nominal e em 1 032 no código, cabendo ao desempate fixo por ID completar essas seleções. Entre os escolhidos, 155 no nominal e 779 no código já estavam ausentes da residência da própria C286 no fim do prefixo. A projeção oferece a sua materialização, sobrevivência ao prefill153 e quaisquer cópias sem custo. Com a mesma convenção otimista de colocação e reposição, a seleção por hotness da própria C294 exigiu 1 106 e 1 179 cargas em nominal e código. [Screen de controlo](causal_prefix.md) · [Avaliador das reposições](cache_bound.py)

**Compatibilidade e decisão.** As rotas que o avaliador serve são as do journal C294 R0. A classificação vem exclusivamente do prefixo C286. Os logits completos de 33 posições de E diferem bit a bit dos de R0 nos dois casos. O argmax coincide em 32/33 posições nominais e 33/33 de código. Estas 33 posições começam no fim do incremento; a sua comparação não observa as rotas de preparação do prefixo. A regra transferida falha mesmo com as concessões descritas. Para qualificar uma regra própria de frequência cumulativa R0, é necessário registar antes do incremento as contagens inteiras completas por camada/expert das linhas que o target efetivamente roteou. Para a regra de retenção online ao longo do prefixo é necessária também a ordem das procuras. A associação futura entre experts e tempos requer ablação e verificação dos custos do serviço. O NO_GO físico original do custo de C286 continua circunscrito à sua própria intervenção em E. M3 PARTIAL e M4 NOT_MET. [Resultado de custo C286](../../results/c286-logical-route-policy-cost-20261006/paired-analysis.json)

## Reprodução

```sh
python3 -B research/qualification-retake/cross_prefix.py \
  --historical-results "$TESY_RESULTS_HISTORICOS" --source-backend "$TESY_C284_BACKEND" \
  --new-output-dir "$NOVO_CROSS_PREFIX"
```

SHA-256 do recibo `1288f59b44a1ddd69eecd52778f4f9b56e354d60973fdbf48c25175fe43796f4`. A execução do screen tomou 0,93 s e 114 040 KiB de RSS máximo, com zero payload de pesos, forwards ou GPU. A contagem é FORMAL condicional a dois arquivos históricos; as taxas da tabela são tetos de transporte.
