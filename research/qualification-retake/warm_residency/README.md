# Cache de vítimas no incremento quente de R0

**NO_GO para construir a L2 global de vítimas segundo o filtro conjunto de decode C294.** Com 3 GiB, nenhum caso evita 20% das leituras. Entregar todo o saldo de E20 ao payload leva o nominal a 22,57%, mas o código chega a 14,22%. Em cada braço os limites inferior e superior coincidem durante o decode para qualquer conteúdo ou ordem da L2 antes do incremento. A decisão diz respeito a esta LRU e à agenda primária observada. [Pré-registo](protocol.md) · [Recibo por braço, fase e dispositivo](evidence-r1/receipt.json)

| Braço C294 | Cargas no prefill / decode | Hits de decode a 3 GiB | Hits de decode com saldo E20 | Cópias de vítimas no decode com saldo E20 |
|---|---:|---:|---:|---:|
| Nominal 2 ON | 1 043 / 1 081 | 184 (17,02%) | 244 (22,57%) | 1 042 |
| Nominal 3 ON | 1 043 / 1 081 | 184 (17,02%) | 244 (22,57%) | 1 042 |
| Código 2 ON | 2 106 / 1 308 | 132 (10,09%) | 186 (14,22%) | 1 276 |
| Código 3 ON | 2 106 / 1 308 | 132 (10,09%) | 186 (14,22%) | 1 276 |

**TRACE_DERIVED / FORMAL condicional à agenda.** O filtro desta unidade verifica a redução das cargas do **decode** nos dois casos. O limiar C106 aplicava-se ao seu workload inteiro e exigia também tempo exposto compatível com ≥8% no pedido e contabilização de igual memória. Na janela C294 completa (incremento de 153 mais 32 passos) as quatro percentagens admissíveis têm intervalos conservadores porque o estado inicial da L2 no prefill é desconhecido.

| Workload e cap | Cargas primárias | Limites de hits no prefill | Limites de hits na janela completa | Fração na janela completa |
|---|---:|---:|---:|---:|
| Nominal 3 GiB | 2 124 | 157–416 | 341–600 | 16,05–28,25% |
| Código 3 GiB | 3 414 | 289–495 | 421–627 | 12,33–18,37% |
| Nominal E20 | 2 124 | 177–536 | 421–780 | 19,82–36,72% |
| Código E20 | 3 414 | 289–618 | 475–804 | 13,91–23,55% |

Uma L2 deliberadamente vazia no início do incremento dá 459/2 124 hits no nominal e 475/3 414 no código sob E20. Para identificar o número da janela completa a partir de um prefixo já quente, é preciso observar a lista ordenada da L2 de vítimas ao entrar na chamada, ou o fluxo anterior das expulsões e consultas que a determina. Os intervalos acima contêm todas as inicializações; os extremos do intervalo agregado não têm garantia de serem simultaneamente atingíveis. C123 e C135 fecharam a L2 alimentada por cargas concluídas. O C106 testou também inserção por expulsão num workload 189+32. C164 fechou a política primária de 52 slots CPU e 44 GPU nos seus holdouts. A partilha ideal de 1 440 slots entre camadas já tem um limite no transporte USB. [C106](../../../results/c106-l2-fixed-trace-screen-20260928T2340Z/decision.json) · [Errata C108](../../../results/c108-trace-errata-20260929T0805Z/analysis.json) · [C123](../../../results/c123-warm153-decode-trace-20260929T1450Z/decision.json) · [C135](../../C135-C136-SLOTS40-RESIDUAL-DECODE-20260929.md) · [C164](../../C164-REPLAY-AND-POLICY-DECISION-20260930.md) · [Partilha ideal](../cache.md)

**Custo ainda a pagar.** O ponto preventivo E20 é 20 937 965 568 B. O maior pico contemporâneo usado foi 15 933 677 568 B no gate C270, contra 15 728 447 488 B na conversa de R0. Sobraram 5 004 288 000 B antes de contabilizar a L2. Cabem 378 vítimas inteiras (4 996 857 600 B), com 7 430 400 B para todo o restante overhead. No nominal, poupar 3,225 GB lógicos de leituras de decode exigiria materializar 13,774 GB de vítimas, 752 entradas provenientes de slots CPU e 290 de CUDA. Em código são 2,459 GB contra 16,868 GB (926 CPU, 350 CUDA). Uma cópia válida já presente na L2 dispensa nova materialização. Sem uma cópia codificada retida no host, conservar uma vítima em CUDA exige ainda fazer chegar esses bytes à RAM antes de sobrescrever o slot. Um hit continua a exigir entregar os bytes ao primário. Estes são volumes lógicos. Não houve medição de tráfego físico, de tempo de cópia exposto, de trabalho útil sobreposto nem da diferença no relógio do cliente. [Gate E20](../nvme_r0_gate/e20_measured/receipt.json) · [Conversa contemporânea](../nvme_conversation/evidence-20261124-r1/evidence.json)

Protocolo `0f69b66e`, replay `8801c80c2ef716672f16c03f2c4fdc1a179af958`. Quatro braços com doze ficheiros validados por hash e tamanho. O teste de intervalos enumerou 1 296 palavras de quatro operações e dez estados iniciais cada para três experts e capacidade dois, incluindo 3 834 prefixos ambíguos. A execução demorou 0,479 s, atingiu 44 480 KiB de RSS e produziu um recibo de 27 366 B (SHA-256 `85ea2f4b653ee91dba8ef296a9f4a38056680bcdc94c1f8367423aa7fba7047b`). Não abriu pesos nem usou GPU. M3 PARTIAL e M4 NOT_MET. [Reconstrução independente do primário](../cache_boundary.md)

```sh
python3 -B research/qualification-retake/warm_residency/replay.py \
  --raw-dir "$TESY_C294_RAW" --new-output-dir "$NEW_REPORT"
```
