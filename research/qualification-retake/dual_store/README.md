# Escolha do SSD na primeira posição de decode de C135

**NO_GO sob as durações medidas em separado.** Em ambos os pares, o oráculo escolheu **0 das 60 leituras no USB**. Encaminhou os 264 384 000 B úteis (264 630 272 B pedidos com alinhamento) para o NVMe. Nenhuma das 16 barreiras terminou mais cedo. O limiar pré-registado exigia pelo menos 5% de redução no serviço modelado do NVMe em cada par. [Protocolo](protocol.md) · [Recibo por geração e componente](evidence/receipt.json)

| Par histórico | USB simulado (ms) | NVMe simulado (ms) | Melhor mistura simulada (ms) | Ganho | USB medido, submit até retorno (ms) | NVMe medido, submit até retorno (ms) |
|---|---:|---:|---:|---:|---:|---:|
| USB 1 / NVMe 2 | 491,233 | 143,882 | 143,882 | 0% | 493,418 | 145,416 |
| USB 4 / NVMe 3 | 495,990 | 143,175 | 143,175 | 0% | 498,305 | 145,518 |

A call 3 corresponde à posição 2197, depois do prefill 5+148. Cada geração conserva o mesmo expert, slot, destino e os três pedidos síncronos gate/down/up. A simulação admite as gerações de cada grupo ao mesmo tempo, escolhe a menor duração histórica de cada componente e, em empate, usa o NVMe. A soma dos 16 máximos por grupo mede o serviço simulado. As duas últimas colunas somam as janelas históricas desde a submissão até ao retorno de todos os jobs de cada grupo. [Sonda e plano originais](../nvme_admission/README.md)

Catorze grupos tinham um único expert. No modelo NVMe, os dois grupos com dois e quatro experts ocupam, juntos, 40,491 ms (28,14%) no primeiro par e 39,587 ms (27,65%) no segundo. São os únicos que permitem leituras simultâneas nos dois discos mantendo as três chamadas do worker em série. A experiência histórica colocou todos os pedidos de um braço no mesmo disco. Uma distribuição simultânea poderia alterar as filas e o serviço de ambos. Para atribuir um ganho a esse efeito seria preciso observar pedidos concorrentes divididos entre os dispositivos, preservar as barreiras e comparar com o NVMe contemporâneo. O resultado atual encerra apenas a seleção por duração fixa nesta posição. A qualificação do pedido mantém M3 PARTIAL e M4 NOT_MET. [Capacidade por fase](capacity.md) · [Antecedente sobre réplicas](antecedente.md)

## Reprodução

Congelamento do protocolo em `393d8108adc8b59b00826d3cb5cda62a3fd6a362`. As duas reproduções usaram a checkout limpa `2d5a9238282107460f194e9ed052cf27598f7228` e produziram o mesmo SHA-256 `789ba53d7e2e686fdfa6af16fbda776dc9e61bfaa845364e47f05974a88222bb`. Cada execução demorou 0,06 s. Os picos de RSS foram 20 808 e 21 252 KiB. O manifesto dos quatro braços, do freeze e do recibo da família consta do recibo publicado. O replay usou somente esses registos e o plano, com zero forwards, pesos ou GPU. [Controlos históricos](../nvme_admission/evidence-20261124-r1/io.json)

A partir da checkout de medição, apontar `TESY_C135_ABBA_RAW` à pasta privada arquivada `part-01/c135-abba/r1` e `TESY_DUAL_STORE_OUT` a um diretório novo fora da checkout e dos raws, cujo pai já exista.

```sh
LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 python3 -B \
  research/qualification-retake/dual_store/screen.py \
  --raw-dir "$TESY_C135_ABBA_RAW" --new-output-dir "$TESY_DUAL_STORE_OUT"
```
