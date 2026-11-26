# Todas as reservas de disco no prefill nominal

**REPRODUZIDO.** O replay da política que conserva o estado do prefill identifica 1 058 reservas que precisam de disco e 226 cobertas pelo banco estático escolhido em T1. A lista privada mantém a ordem das reservas nos 1 331 callbacks originais, inclusive os sem trabalho de transporte. O ensaio seguinte pode abrir a fila inteira de cada chamada aos quatro workers para medir o serviço sob essa condição. Continua a haver uma fronteira entre as duas chamadas. [Protocolo](protocol.md) · [Recibo com os custos por tier](receipt.json)

| Chamada | Tokens da tile | Disco | Banco |
|---|---:|---:|---:|
| 5 | 5 | 34 | 25 |
| 148 | 32 | 281 | 55 |
| 148 | 32 | 64 | 6 |
| 148 | 32 | 174 | 24 |
| 148 | 32 | 124 | 23 |
| 148 | 20 | 381 | 93 |

As reservas de disco com destino CPU e CUDA são, respetivamente, 26 e 8 na primeira chamada, 635 e 389 na segunda. A call 148 contém 441 reservas de preload, contando ambas as fontes. Cada reserva mantém o expert, slot, geração, vítima, causa, origem, ordinal da reserva e os três SHA-256 de componente e intervalos do GGUF e do pack. O plano conserva os ranks e os limites do cálculo; a camada 35 só está presente na última tile e executa uma linha. [Gestor e conservação das decisões de R0](../../../replay/README.md)

| Fase | Payload de disco (B) | Pedido GGUF alinhado (B) | Pedido do pack (B) |
|---|---:|---:|---:|
| 5 | 449 452 800 | 449 880 064 | 449 544 192 |
| 148 | 13 536 460 800 | 13 548 785 664 | 13 539 213 312 |
| Total | 13 985 913 600 | 13 998 665 728 | 13 988 757 504 |

Os bytes são calculados a partir dos descritores. A proposta de conceder elegibilidade antecipada dentro da chamada modifica o agendamento das leituras. Para atribuir tempo de produto seria necessário voltar a impor as dependências do pedido e cobrar o banco, os SET e o último leitor dos pesos.

## Reprodução

O protocolo foi fixado em `8d26cdc3` e o código em `4cd4dcf4b876f13bd3cabd44e5b17d5cbb49b9ef`. As duas execuções em checkout limpa duraram 0,95 s cada, com 84 280 e 84 304 KiB de RSS. O plano privado tem 1 726 064 B e SHA-256 `f54b60d5389d4ff503c978e9eed6065e87e0c08a3a245de17d1f59f58e3a152f`; o recibo das duas execuções é idêntico (`cdeae2ad6b637c11c1f9dc51ab34664ca756f468ab334f209cca64abd5f3739b`). Apenas metadados foram lidos. Fornecer o manifesto da parte 63 na sua raiz, o ficheiro integral-index.json de C290 e o recibo de colocação integral no NVMe. Cada reprodução exige um destino novo.

```sh
p=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/prefill_frontier/transport/prepare
python3 -IB "$p/test_plan.py" -q
env LC_ALL=C PYTHONUTF8=1 PYTHONCOERCECLOCALE=0 OPENBLAS_NUM_THREADS=1 \
  python3 -IB "$p/plan.py" --part63 "$PART63" --index "$C290_INDEX" \
  --placement "$PACK_PLACEMENT_RECEIPT" --new-output-dir "$NEW"
```
