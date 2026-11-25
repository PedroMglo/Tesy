# Quanto acrescenta uma segunda melhoria à primeira?

**A política de expulsão acrescenta um ganho à cache em RAM.** No replay do nominal, com o mesmo banco de 353 experts e o mesmo estado primário exigido no primeiro decode, escolher primeiro uma vítima recuperável em RAM poupa **mais 50 leituras do disco no prefill e 169 no decode** face à LRU com esse banco. O custo das 172 leituras de disco e 88 entregas de RAM para repor os residentes de R0 está incluído. Esta combinação ainda precisa de 1 184 e 974 leituras do disco, acima dos gates exploratórios de 808 e 872. **NO_GO neste cenário a 4,5 GB/s e decode a exatamente 6 tok/s.** O ganho marginal de serviço fica disponível para uma combinação que altere o preço, a seleção ou o restante do pedido. [Protocolo causal](protocol.md) · [Contagens por braço](evidence/causal.json)

## O que se acumula na mesma trajetória

Dados **SIMULADOS** sobre os top-4 efetivos de um único T2 natural. Em cada célula estão as admissões que requerem o NVMe, em prefill / decode. Absorver uma admissão pelo banco ainda obriga a entregar as três componentes corretas ao destino. R0 observado admitiu **1 263 / 1 091** gerações. O replay das outras linhas mantém simultaneamente os experts de cada wave, 40 slots por camada, 5+148 e as 46 avaliações de decode. A geometria do kernel continua reservada à eventual validação do backend. As agendas simuladas usam carga à procura e dispensam os preloads e o parking físico de R0. A atribuição do ganho marginal compara apenas as duas políticas com a mesma agenda, banco e regras de restituição.

| Política | Continuar com os residentes produzidos | Repor os residentes R0 antes do primeiro decode | Leituras do disco incluídas para repor |
|---|---:|---:|---:|
| LRU, banco desligado | 1 184 / 1 411 | 1 373 / 1 333 | 189 |
| LRU, mesmo banco de 353 | 1 049 / 1 225 | 1 234 / 1 143 | 185 |
| Expulsar primeiro os que têm cópia em RAM, mesmo banco | **1 012 / 1 061** | **1 184 / 974** | 172 |

Mantendo a cache produzida, a mudança de vítima poupa 37 e 164 leituras relativamente à LRU com o mesmo banco. Esse braço precisa de pelo menos **5,631 GB/s úteis** só para ler o prefill no tempo disponível. Se for exigido o conjunto R0, precisa de **6,588 GB/s**. Os acertos correspondem a transferências e o preço de construir o banco em T1 também pertence à comparação de produto. A igualdade que a coluna de reposição impõe é de membros por camada. O custo de permutar fisicamente slots, validar o estado do primeiro decode, reconstruir gerações e executar cópias ou kernels continua em aberto.

## Até onde se pode chegar com estas mesmas cópias em RAM?

**FORMAL no problema lógico de residência.** O ótimo com as posições do pedido conhecidas antecipadamente necessita de 776 leituras no prefill, com o conjunto R0 reposto, e 641 no decode que lhe sucede. Ambos os mínimos são compatíveis através do estado de fronteira. Sem o banco, os mínimos sobem para 927 e 784. A diferença entre exigir a fronteira e lhe dar liberdade no prefill é de 42 leituras no ótimo com banco. As 776 leituras totalizam 10 258 099 200 B úteis. No cenário de 4,5 GB/s e 47/6 sobram **432 207 414 B, ou 96,046 ms**, para trabalho que não se sobreponha à leitura. A taxa mínima é **4,318 GB/s** mesmo concedendo tempo zero ao restante trabalho. A diferença de 408 leituras entre a política causal com reposição e o ótimo no prefill identifica o espaço que uma melhor decisão de residência teria de explorar. [Critérios anteriores à medição](oracle-protocol.md) · [Mínimos por tier](evidence/oracle.json)

| Banco ao POST | Prefill, saída livre | Prefill com fronteira R0, CPU / CUDA | Decode desde a fronteira, CPU / CUDA | Gates conjuntos de volume |
|---|---:|---:|---:|---|
| Vazio | 867 | 599 / 328 | 548 / 236 | NO_GO no prefill |
| Últimas 353 vítimas de T1 | 734 | 490 / 286 | 429 / 212 | **HEADROOM_ONLY** |

Uma chave em RAM pode ser relida gratuitamente no problema de contagem de acessos ao disco. Substituir cada ocorrência dessa chave por um pin temporário exclusivo preserva o número de slots exigidos nessa wave. Cada pin temporário provoca uma inserção de custo lógico unitário, subtraída ao total. Os únicos itens que interessa manter entre waves são os de reposição paga. No outro sentido, uma agenda sobre os pins temporários pode recarregar a chave do banco em cada ocorrência. Isto reduz o problema ao ótimo de substituição por uso futuro mais distante com os pedidos simultaneamente protegidos. A fronteira exigida é uma última wave por camada com o conjunto R0 e o descarte gratuito dos excedentes. O teste contra enumeração exaustiva verificou 1 944 combinações pequenas de fluxos, estados iniciais e bancos. A prova cobre admissões ao disco na relaxação. Os tempos de prefill e decode continuam por medir numa política executável. [Implementação](oracle.py) · [Enumeração independente](test_paid_minimum.py)

## Combinar com o layout que já tinha dado um ganho

**MEDIDO noutra campanha.** Os dois pares C293 deram reduções de 7,004% e 7,941% no tempo total do nominal com 153 tokens fornecidos e 32 avaliações de decode. Em código deram 5,219% e 6,877%. Conservaram as 33 linhas completas de logits. O contraste C293 manteve as identidades e o número de admissões. O ganho integrado do mecanismo ficou abaixo do gate original. A colocação do modelo no NVMe interno restabelece o controlo físico e tem contribuição zero para as alegações de engenharia desta unidade. [Oito braços C293](../../../../C293-INTEGRATED-EXPERT-STORE-COST-NO-GO-20261006.md) · [Pares originais](../../../../../results/c293-integrated-expert-store-native-cost-20261006/paired-analysis.json)

**ESTIMADO para escolher o próximo ensaio.** Aplicámos separadamente os preços de serviço por destino de cada braço C289 às faltas remanescentes. Cada tier C289 serviu 256 admissões, em 64 grupos de quatro. A conta em segundos é a soma, para CPU e CUDA, de admissões residuais × tempo de serviço observado no tier / 256. A1/A4 usam o layout original. B2/B3 usam o pack de uma única leitura por expert. Todos os braços deste cenário concedem o banco, o grafo e a sua preparação gratuitamente. O denominador de prefill no T2 é 2,375624 s a 47/6. [Serviço separado nos quatro braços](../../../../../results/c289-lossless-service-resource-qualified-20261006/paired-analysis.json)

| Faltas CPU / CUDA de prefill | A1 (s) | B2 (s) | B3 (s) | A4 (s) |
|---|---:|---:|---:|---:|
| 650 / 362 com a política causal e saída livre | 4,672 | 3,643 | 3,359 | 4,748 |
| 763 / 421 com a política causal e reposição | 5,466 | 4,262 | 3,930 | 5,555 |
| 490 / 286 no ótimo com reposição | 3,582 | 2,797 | 2,578 | 3,641 |

O pack ajuda nos dois pares deste cenário. Mesmo o melhor preço transferido para o ótimo deixa 203 ms por recuperar antes de pagar o resto da fase. A taxa efetiva, a composição dos grupos e a falta de informação futura na implementação ainda podem mudar o resultado. Uma comparação física útil mede o efeito marginal do pack **sobre as faltas e os acertos que restam** na mesma agenda. O desenho prevê a agenda original e a política causal com banco, cada uma com GGUF original e pack exato, os quatro workers e o mesmo envelope de recursos. A ablação do banco sob a agenda nova isola a parte de recuperação da RAM. Medir os bytes entregues, as cópias para CPU/GPU e a última publicação por wave antes de atribuir tempo à conversa. Começar pela mesma seleção de experts e grupos capturados, sem novo forward. Um resultado de produto exige também os pedidos naturais, o outro caso, os validadores e o relógio do cliente.

## Reprodução e proveniência

Protocolo causal em `74c470fb` e código em `e4014831`. Os dois processos em árvore limpa levaram 0,67/0,70 s com até 75 212 KiB de RSS. O recibo causal tem SHA-256 `5a98dfe45eae6900c68b8ca6bea899d3222c1769f3ca99ccf1ab79eddd53c796`. Protocolo do ótimo em `927bdb6b`, código em `68c90e45`. Duas tentativas com o Python do sistema terminaram na importação indireta de NumPy antes de ler os dados. Os dois recibos de falha ficam em evidence. Usando o ambiente do projeto, as execuções seguintes duraram 0,64/0,61 s, até 90 696 KiB, e geraram resultados idênticos com SHA-256 `727f262d965b40a410d967d73d4c7fadb75161776ddadd47321d49dee59b9db6`. Zero novos forwards, leitura de pesos, computação GPU ou Actions. M3 PARTIAL, M4 NOT_MET.

```sh
unit=research/qualification-retake/phase_fd/integrated/t1_primary_victim
python3 -IB "$unit/screen.py" --part "$ARCHIVE/part-40" --model "$MODEL" \
  --inventory "$INVENTORY" --prepared-dir "$SEAL" --score-dir "$SCORE" --new-output-dir "$CAUSAL"
env LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  "$TESY_VENV/bin/python" -IB "$unit/oracle.py" --part "$ARCHIVE/part-40" --model "$MODEL" \
  --inventory "$INVENTORY" --prepared-dir "$SEAL" --score-dir "$SCORE" \
  --causal-dir "$CAUSAL" --new-output-dir "$NEW_ORACLE"
```
