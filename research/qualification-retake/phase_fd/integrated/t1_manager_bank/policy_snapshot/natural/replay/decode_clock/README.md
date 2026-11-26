# O decode continua limitado pelo serviço dos experts comuns

**Com o tempo de READ do GGUF observado em R0, a prioridade com banco de 353 vítimas fica aquém de 6 tok/s.** Nas 46 avaliações de decode, todos os 797 experts que a alternativa ainda pediria ao disco têm uma leitura contemporânea do mesmo expert, na mesma camada e avaliação. Mantendo o preço dessas leituras e dos SET comuns no mesmo tier, o decode demoraria pelo menos 8,678 s para os 47 tokens, no máximo **5,416 tok/s**. É uma poupança máxima condicional de 1,441 s frente aos 10,118461 s medidos em R0. O limite encontra-se 0,844 s acima de 47/6 e 2,718 s acima dos 5,959 s permitidos pelo cruzamento de 7,887 tok/s quando o prefill conserva G a 4,5 GB/s. O trabalho novo e o transporte do banco tiveram preço zero neste cálculo. [Protocolo](protocol.md) · [Cruzamento de prefill](../../accounting.md) · [Recibo com as alternativas e ambos os denominadores](evidence/receipt.json)

| Política e origem | Admissões | Disco | Novas neste sítio | Piso GGUF 1× (s) | Piso GGUF 0,8× (s) | Piso sem preço de READ do pack (s) | Cruzamento próprio (tok/s, D=47) |
|---|---:|---:|---:|---:|---:|---:|---:|
| R0, disco | 1 091 | 1 091 | 0 | 10,035 | 8,604 | 2,886 | 8,774 |
| R0, banco | 1 091 | 919 | 0 | 9,371 | 8,073 | 2,886 | 8,086 |
| Prioridade, conserva, disco | 1 196 | 1 196 | 227 | 9,426 | 8,109 | 2,840 | 8,876 |
| Prioridade, conserva, banco | 1 196 | 797 | 227 | 8,678 | 7,509 | 2,840 | 7,887 |
| Prioridade, repõe, disco | 1 190 | 1 190 | 219 | 9,450 | 8,128 | 2,843 | 8,970 |
| Prioridade, repõe, banco | 1 190 | 799 | 219 | 8,699 | 7,527 | 2,843 | 7,887 |

**Que trabalho mudou?** Das 1 196 admissões com prioridade e estado conservado, 969 têm um par no sítio R0, 122 passaram a dispensar reserva e 227 são novas. Todas as 227 novas recorrências são recuperáveis no banco, 187 nas camadas CPU e 40 nas CUDA. Entregam 3 000 758 400 B ao primário e o seu tempo de SET fica desconhecido. No total são 399 entregas do banco (5 274 460 800 B) e 797 gerações do disco (10 535 702 400 B de payload). O primário recebe 15 810 163 200 B. O número de faltas de disco cai mesmo quando o número de entregas sobe.

O servidor mediu 10,118461 s. A união de 1 656 callbacks ocupa 7,800219 s. Ao conservar o exterior e conceder 1 μs de arredondamento, ficam 2,318241 s de custo fixo. Cada callback só paga o maior entre a cadeia serial mais longa e a soma de trabalho dividida por quatro. Para o candidato com banco, os READ comuns somam 7,895946 worker-s e os SET comuns 0,701341 worker-s; essas somas têm domínios simultâneos. No controlo R0 a diferença entre a união das callbacks e o piso cobrado é 83,858 ms. Esse valor agrega o trabalho e a coordenação que a fórmula relaxa; não identifica isoladamente o custo de coordenar. Alterar a prioritização pode mudar o paralelismo e o preço das leituras.

Só 71 das 969 admissões comuns usam o mesmo slot físico. Ao dispensar todo o custo de SET dos outros destinos, o piso de 1× ainda é 8,207 s (máximo 5,727 tok/s). A 0,8× e conservando o preço de SET no tier, restam 324 ms de parede para atingir 6 tok/s, cerca de 271 μs por admissão se repartidos igualmente. O cruzamento continua a faltar por 1,550 s. A convenção D=46 dá 7,719 tok/s para a prioridade com banco e o mesmo orçamento de 5,959 s. As duas convenções usam a própria contagem em D/v. O alvo de produto usa 47 tokens.

**Preço do pack ainda desconhecido.** Com as leituras gratuitas, o piso de 2,840 s deixa **3,119 s de caminho crítico** para alcançar o cruzamento. Nesse saldo têm de caber as 797 leituras de 13 221 888 B cada, o custo adicional das 399 entregas do banco incluindo os 227 SET novos, e a coordenação ainda exposta. O primeiro dado discriminante é a duração das leituras físicas dessas 797 entradas do pack integral pela ordem dos grupos reais, com quatro workers, face às três leituras GGUF correspondentes. Se o transporte couber, faltará medir a publicação e o consumidor nos respetivos tiers.

## Reprodução

Congelados o protocolo em `70319745` e a implementação em `0e83277d874c591bf4fceda379cd2c3598ed7085`, árvore `ee45e1ae03be8788483d9f9f7ff5765f13813dbf`. As duas reanálises CPU da parte 63 produziram o mesmo recibo de 122 837 B, SHA-256 `f637152c0915ccbf33d4f70e101e9910a6aab2edd2d925a93f7ed6f250fe8f99`. Durações de 1,04 e 1,00 s, RSS máximos de 72 708 e 72 240 KiB. Ambas usaram os mesmos dados físicos históricos. A operação deixa os pesos fechados.

```sh
A=/mnt/sdisk-ssd-ext/Tesy/outputs/qualification-20261124-nvme-01/part-63
P=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/replay/decode_clock
OPENBLAS_NUM_THREADS=1 python3 -IB "$P/screen.py" \
  --family "$A/tesy-policy-natural-physical-20261125-r02" \
  --pair "$A/tesy-policy-natural-account-20261125-r02/receipt.json" \
  --cost "$A/tesy-policy-natural-cost-20261125-r02/receipt.json" \
  --new-output-dir "$NOVO"
```
