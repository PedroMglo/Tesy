# A fusão preserva todos os bits nos casos de falha?

**GO_REAL_TILE.** Nos 96 casos sintéticos, cada um dos quatro modos produziu 2 880 312 B, todos idênticos, SHA-256 1c64f50035a96610ca96e9b77af93acd6c50c5ccae41cafbe6cd04473066ef46. Nos 18 casos previstos, a fusão foi executada uma vez. Nos restantes 78 casos o contador da variante ficou a zero. A referência independente usou o GGML C269 original. [Enumeração dos casos e resultados](physical-r01/receipt.json) · [Regras congeladas](protocol.md)

| Modo | Casos | Resultados não finitos | Fusões observadas |
|---|---:|---:|---:|
| C269 original | 96 | 0 | 0, símbolo ausente |
| Candidata com os dois cortes desligados | 96 | 0 | 0 |
| Apenas o corte por MMID | 96 | 0 | 0 |
| Corte por MMID e fusão de seis nós | 96 | 0 | 18 |

**MEDIDO na CPU do portátil.** Cada caso compara as vistas observáveis da cauda do FFN, incluindo o efeito de bias positivo, negativo, subnormal e zero com sinal no produto da máscara e na soma posterior. A fixture exercita 1, 2, 20 e 32 posições, equipas de 1 e 8 threads, IDs ativos/estacionados que mudam entre execuções do mesmo grafo, consumidor externo, saída intermédia pedida, operação intercalada, padding e sobreposição de memória. Os contadores são de diagnóstico. A duração de 1,820 s cobre toda a compilação e execução da família. O pico de memória foi 129 572 864 B e o cgroup usou zero swap. Não houve pesos reais, GPU compute ou forwards do target. A DSO candidata é 526a4684edd7eb0e60fb16dabb99d23198f9ede8822ef716c480b5e853c3a208. [Operador e controlos](fixture.cpp) · [Alteração no kernel](kernel.py)

A revisão de medição é cb0ca719361a57d3bbec11105e2ef2227913cfce. O arquivo privado qualification-20261124-nvme-01/part-26 reúne o grafo e a fixture, 46 ficheiros, 16 028 671 B, manifesto ef3aee9fcce9ff6e22188612187c86e8232391994e7781d65ddd6574a70b75f1. A validação do arquivo recalcula os quatro resultados, cada intervalo de bytes, o respetivo hash e os contadores. O recibo terminal é c7926f18eb558240f3d14a2be2ed12872de98b2fbfbf5ed6b57b51d9140960bc. O ensaio seguinte usa dados C266 reais com o mesmo scheduler e verifica se os seus endereços de buffers satisfazem os guardas do candidato. [Gate da tile CPU0](../real_tile/protocol.md)

```sh
python3 -IB research/qualification-retake/parked_fusion/numerical/build.py \
    --verify-output-dir "$TESY_PART26/tesy-parked-fusion-numeric-20261125-r01"
```
