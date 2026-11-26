# Cantidade de pesos que a memória combinada pode poupar ao SSD

**INCONCLUSIVE para a latência.** Para a mesma rota de T2, mesmo uma cache perfeita com 161 slots GPU e 10 GiB totais de payload acessível em RAM teria de obter pelo menos **24,416 GB** de pesos até ao primeiro conteúdo final. Com 20 GiB esse mínimo baixa para **8,963 GB**. São pisos com conhecimento da mensagem futura e entrada gratuita. A 4,5 GB/s, ambos ficam abaixo do próprio piso PCIe do LRU de 161 slots (6,883 s). Este crivo justifica medir primeiro a cópia real a partir do mmap. O desempenho natural continua dependente do estado que T1 realmente deixa em RAM, da latência de servir as páginas e do trabalho que se consegue sobrepor. [Protocolo](protocol.md) · [Recibo com os 24 casos](result.json) · [Quatro combinações de política e tamanho](../classlru/README.md)

| RAM ideal para pesos | Slots GPU | Origem até ao primeiro final | Mínimo da origem em 10 s | Origem durante o decode, com entrada ideal própria | Mínimo da origem para 47 saídas a 6 tok/s |
|---|---:|---:|---:|---:|---:|
| 10 GiB | 128 | 25,288 GB | 2,529 GB/s | 11,910 GB | 1,521 GB/s |
| 10 GiB | 161 | 24,416 GB | 2,442 GB/s | 11,474 GB | 1,465 GB/s |
| 20 GiB | 128 | 9,399 GB | 0,940 GB/s | 1,177 GB | 0,150 GB/s |
| 20 GiB | 161 | 8,963 GB | 0,896 GB/s | 0,740 GB | 0,094 GB/s |
| 32 GiB | 128 ou 161 | 0 | 0 | 0 | 0 |

Até à primeira peça foram precisas 2 464 chaves distintas em 10 162 procuras por sítio. Para poder iniciar com todas as chaves necessárias, além dos 161 slots GPU, seriam precisos 2 303 experts em RAM. A hipótese de 32 GiB dedica toda a RAM nominal a esses pesos e permite escolher exatamente essas chaves antes do pedido. Um processo E10 pode usar páginas já quentes debitadas a outro cgroup. Para aplicar as linhas de 10 e 20 GiB à máquina é preciso conhecer a residência acessível total. Os bytes da tabela passam ao domínio físico apenas sob a correspondência 1:1 especificada no protocolo. No T2 completo são 2 470 chaves para 10 450 procuras. O prefill sozinho tocou 1 751 chaves e o decode 1 842. Os estados iniciais ideais de dois recortes podem ser diferentes.

Sob LRU, a 16 GB/s brutos para a GPU e 4,5 ou 8 GB/s constantes para o disco, o maior dos dois pisos deixa **no máximo 1,710/3,117 s** de trabalho serial adicional até à primeira peça para 128/161 slots. Durante o decode completo sobram no máximo **2,361/3,820 s**. A cache em CPU e a GPU interagem. O máximo das duas obrigações continua válido porque pertence ao mesmo relógio. Mesmo que as políticas ótimas de cada tier sejam incompatíveis, este teto de folga favorece o candidato. A análise de ClassLRU requer o seu próprio payload H2D. O comportamento real com computação, KV e temporários a ocupar RAM/VRAM exige medições.

## Verificação do piso de payload

Cada intervalo entre duas utilizações consecutivas de uma chave oferece uma oportunidade de evitar a leitura seguinte. O primeiro intervalo parte de uma fronteira comum anterior ao primeiro sítio, com a mesma capacidade total. Uma fração mantida durante todo o intervalo poupa a mesma fração de um expert. O ficheiro original tem 108 matrizes disjuntas e cada uma das três componentes é sempre necessária. Em cada fronteira, a soma das frações retidas tem de caber na memória. A matriz dessas restrições tem uns consecutivos em cada coluna (um intervalo por coluna). Por unimodularidade total, a relaxação com capacidade inteira e limites de zero a um tem uma solução ótima inteira. Arredondar a capacidade **para cima** concede até mais um expert. Permitir streaming imediato de cada miss evita forçar a inserção de valores que nunca serão reutilizados.

O solver começa pelas primeiras chaves a serem pedidas. A cada sítio satisfaz os pedidos e escolhe entre os residentes e os recém-servidos as chaves cuja próxima procura chega primeiro. Trocar uma vítima por outra necessária mais tarde nunca aumenta a contagem de hits até à primeira dessas utilizações; as duas escolhas podem então ser conciliadas. Um teste independente enumerou todos os estados de cache, incluindo decisões de bypass, em 343 sequências de três sítios e quatro capacidades. Um segundo controlo fragmentou cada payload em duas e três porções de retenção independente na mesma sequência. [Solver](score.py) · [Testes](test_host_floor.py)

O protocolo foi congelado em `2623f32a` e o solver em `e2990a43`. As duas primeiras execuções calcularam os casos mas falharam ao gerar a hash do script. A correção `29c0a7d3` passou um Path ao leitor e explicitou a condição de trânsito físico. R03 (originais) e R04 (arquivo das partes 97 e 106) produziram recibos idênticos, SHA-256 `961e76f3100016595d1183137e89161ad5ffec0907aa9b245a021c024fcd2ff3`. CPU offline, sem GPU nem leitura de pesos. GB é decimal.

```sh
python3 -IB score.py --p97 "$P97" --p106 "$P106" --inventory "$C283" --new-output "$NOVO"
```
