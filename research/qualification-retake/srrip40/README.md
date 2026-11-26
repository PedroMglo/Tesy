# SRRIP de dois bits nas waves de experts

**NO_GO para SRRIP com esta inicialização e 40 slots por camada.** No C294 nominal, SRRIP poupa 21 admissões no incremento face a R0 mas exige mais 78 no decode e 134 para repor os experts do estado final. Em código poupa 69 no decode, mas exige mais 90 no incremento e 171 na reposição. Cada caso falha uma proteção de fase e ambos falham o critério de redução total de 10%. [Pré-registo](protocol.md) · [Contagens por fase, tier e braço](evidence/receipt.json)

| Caso, braços C294 | Política | Incremento | Decode, 32 passos | Reposição mínima final | Total CPU / CUDA | Total |
|---|---|---:|---:|---:|---:|---:|
| Nominal, 2 e 3 | R0 | 1 043 | 1 081 | 0 | 1 486 / 638 | 2 124 |
| Nominal, 2 e 3 | LRU | 1 071 | 1 091 | 62 | 1 555 / 669 | 2 224 |
| Nominal, 2 e 3 | SRRIP | 1 022 | 1 159 | 134 | 1 618 / 697 | 2 315 |
| Código, 2 e 3 | R0 | 2 106 | 1 308 | 0 | 2 595 / 819 | 3 414 |
| Código, 2 e 3 | LRU | 2 237 | 1 310 | 95 | 2 775 / 867 | 3 642 |
| Código, 2 e 3 | SRRIP | 2 196 | 1 239 | 171 | 2 742 / 864 | 3 606 |

Cada admissão corresponde a 13 219 200 bytes de payload lógico. Os braços 2 e 3 de cada caso coincidem nas contagens. No nominal faltaria eliminar **404 cargas face ao limiar de R0 e 314 face ao de LRU**. Em código faltariam **534 e 329**. Os custos de reposição são o número de identidades de R0 ausentes no fim, com a sua recolocação física gratuita. No diagnóstico por wave de decode, as políticas SRRIP e LRU diferem nos conjuntos de faltas em 297 das 1 152 waves nominais e 286 das 1 152 de código.

R0 é TRACE_DERIVED das publicações históricas. SRRIP e LRU são simulados sobre a mesma ordem física dos 1 440 slots entregues pelo prefixo e sobre os mesmos ranks do target. O ensaio mantém as waves, o incremento, os 32 passos fornecidos e os empates definidos no protocolo. A duração do replay mede o custo da análise. O tempo do pedido, o tráfego físico, o parking, a posição final de cada payload e a exatidão de uma implementação no backend ficam por medir. O ótimo offline com reposição final continua em 1 336 e 2 172 admissões. Para justificar um novo ensaio de substituição é preciso uma política causal diferente que aproxime esse ótimo com proteção das duas fases e custo próprio contabilizado. [Ótimo offline de P a F](../prefill_interval40/README.md)

Pré-registo `54049fe9`, árvore de confirmação `e1402004d3523dd5ea4f882cbabf16fd2900f8d2` no commit `fd80e3699d6ecc496e013124fee2abdca188bae8`. As duas reproduções demoraram 0,65 e 0,66 s, com picos de 81 488 e 81 696 KiB de RSS. O limite por execução era de 120 s, 768 MiB e uma thread. Dez testes locais, zero leituras de pesos e zero forwards.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 120 prlimit --as=805306368 -- \
  python3 -B research/qualification-retake/srrip40/screen.py \
  --family "$WRT40" --historical-results "$C7/results" --new-output-dir "$NEW_OUT"
```

Cada recibo completo tem 341 993 bytes e SHA-256 `fbfc12a0724444fef5a6083b197381f9cd7003dd058dd1499b1487168e6e36e3`. O ficheiro publicado mantém os resultados dos quatro braços, as assinaturas da composição final por política e o índice dos dois originais. Esta comparação reproduz a seleção dos campos do recibo compacto.

```sh
jq -S 'del(.cases[].historical[].policies[].F_slots, .cases[].historical[].policies[].missing_R0_F_by_layer)' \
  "$NEW_OUT/receipt.json" | diff - <(jq -S 'del(.full_receipts)' \
  research/qualification-retake/srrip40/evidence/receipt.json)
```
