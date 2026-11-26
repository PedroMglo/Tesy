# Que experts CPU podia T1 ter antecipado?

**A recência das tiles do próprio T2 cobre 0 das 375 primeiras procuras CPU estritas.** Cada uma usa um par (camada, expert) ausente à entrada e pedido pela primeira vez nessa callback. O cruzamento com todos os ranks das tiles anteriores de ambas as chamadas, 5 e 148, dá o mesmo zero. A conclusão vale para a regra literal de repetir um expert já pedido pela mesma camada. Um preditor capaz de propor pela primeira vez outro expert teria uma hipótese diferente. [Cortes de primeira procura](README.md)

**O banco histórico de 353 vítimas cobriria 65 das 375.** O revisor comparou o início de T2 da parte 63 com o da execução P na parte 97. Coincidem os 1 440 slots, com o mesmo expert e geração, todos READY e sem claim, com filas vazias. Coincidem também os 7 012 quartetos top-4 ordenados, dos quais 5 356 pertencem ao prefill. Aplicado a essas identidades, o banco selado na parte 63 cobre 126 das 852 primeiras faltas de qualquer wave ou tier (96 CPU e 30 CUDA). Nas 567 procuras estritas, cobre 65 CPU e 21 CUDA. A comparação usa identidades, sem transportar timestamps entre processos. [Estudo original](../../../../../../../layer_major_entry/README.md) · [Recibo do cruzamento](last353.json)

| Fonte disponível antes da procura | Chaves CPU das 375 cobertas | Ainda exigem entrega | Outras a antecipar a 8 GB/s | Outras a antecipar a 4,5 GB/s |
|---|---:|---:|---:|---:|
| Mesmo expert da camada numa tile anterior de T2 | 0 | 375 | 321 | 345 |
| Últimas 353 vítimas distintas do sufixo T1 da parte 63 | 65 | 310 | 256 | 280 |
| Todas as vítimas desse sufixo, retenção e seleção perfeitas | 236 | 139 | 85 | 109 |

O sufixo da parte 63 começa na posição 2047 e termina na 2119. As 73 chamadas até ao selo pré-POST de 47 303 registos contêm 2 156 ofertas READY, com 1 698 identidades distintas. A parte 97 abre o journal em T2. O conjunto de ofertas e o banco que o seu próprio T1 teria produzido permanecem desconhecidos. Para os determinar basta selar a sequência das vítimas READY e a seleção antes do POST nesse processo. [Captura de T1](../../../../../../../phase_fd/integrated/t1_capture/capture.md)

**NO_GO condicional para atingir 10 s só no remap CPU com estas fontes.** Com 90,641 ms disponíveis no P, payloads de 13 219 200 B e circulação obrigatória das chaves em falta depois da procura, cabem 54 ou 30 entregas inteiras aos dois preços. A tabela concede custo zero a todas as chaves cobertas e aos outros remaps CPU. O teto da última linha vale para as vítimas do sufixo observado da parte 63. Antecipar por outra fonte, mudar o estado inicial ou acelerar trabalho fora do remap CPU exige uma medição própria. Esta análise secundária reutiliza os journals existentes, sem execução do modelo. [Hipóteses e relógio do P](README.md)

Duas execuções sem pesos usaram a família original P e a sua cópia arquivada. Os recibos são idênticos, SHA-256 `c63eb5121c53d2f83fe75bf4532afeb912d306987f982f8b36f79e3c30ee80ce`. O destino tem de ser novo. [Verificador](last353.py)

```sh
study=research/qualification-retake/igpu_resident_rank/request_budget/device/pack_native/natural_trace/tier_budget/first_use
python3 -IB "$study/last353.py" --part63 "$ARCHIVE/part-63" \
  --family "$ARCHIVE/part-97/tesy-c281-pack-observer-natural-20261125-r01" \
  --new-output-dir "$NEW"
```
