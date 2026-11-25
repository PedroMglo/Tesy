# A escolha de T1 muda a leitura que o worker faz em T2

**GO para qualificar a entrega CPU por pedido.** Na fixture com o manager C291, usar os bytes escolhidos pela frequência do prefill eliminou três das cinco chamadas `pread` ao pack, mantendo a mesma seleção, memória, captura e agenda da ablação. Escolher por frequência ou por recência exigiu duas leituras no total; a distribuição pelas duas procuras mudou. O novo resultado liga as decisões de um seletor causal reproduzido no T1 real a uma mudança de fonte no worker. [Protocolo](protocol.md) · [Recibo reaberto](result.json)

| Processo | Preads na primeira procura | Preads na seguinte | SET nas duas procuras | Componentes primárias que divergiram do gold |
|---|---:|---:|---:|---:|
| Frequência, servir tudo do pack | 4 | 1 | 15 | 0/120 |
| Frequência, servir os hits da RAM | 1 | 1 | 15 | 0/120 |
| Recência, servir os hits da RAM | 2 | 0 | 15 | 0/120 |
| Frequência, trocar a origem de e36 por e38 | 1 | 1 | 15 | 3/120 |

Os quatro processos capturaram os mesmos 52 876 800 B na origem, mantiveram 39 657 600 B no banco de três entradas e publicaram as mesmas cinco gerações nas duas procuras. Cada leitura evitada corresponde a 13 221 888 B pedidos e devolvidos pelo FD O_DIRECT. Foram 39 665 664 B na ablação de frequência. Os quatro workers usaram o percurso de reservas do C291. No claim, o worker reteve uma referência imutável à origem escolhida. Em seguida, os três SET preencheram o slot reservado, cuja geração voltou a ser validada para publicação. Os 40 vínculos finais, os seus números de geração e as saídas do remap concordaram nos quatro processos. A contraprova isolou exatamente os três hashes de e36.

O caminho de uma recuperação, isoladamente, já tinha prova física na parte 47 e a restauração com permuta e proteção do leitor na parte 58. A prova anterior de alias CPU recuperou o backing sem copiar; o primeiro decode CPU0 real leu e24 do pack. O novo teste usa cópias densas CPU para confrontar duas escolhas e uma ablação de fonte com o mesmo custo de captura. O servidor da parte 97 servia do pack. A parte 106 observou as oportunidades sem instalar um banco no caminho do servidor. [Manager e ablações anteriores](../../../../../phase_fd/integrated/t1_manager_bank/README.md) · [Último leitor e alias](../../../../../phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/cpu_alias/manager/README.md)

**Correspondência com a política do pedido.** O mesmo seletor C++ reabriu os 87 736 eventos do prefixo selado antes do segundo POST, a K=353. Reproduziu as 4 548 ofertas, todas as 2 829 chaves distintas, as duas listas ordenadas de 353 chaves e cada contador de admissão, repetição, rejeição e expulsão. No pedido natural, frequência em vez de recência elevou os primeiros usos CPU estritos cobertos de 65 para 101 e reduziu as entregas de decode CPU possíveis de 143 para 41. O preço temporal de cada fase continua a exigir um teste emparelhado do serviço. [Limites da conversa](../natural_trace/prefill_retention/README.md)

A fixture usa uma camada CPU, tensores primários GGML reais e pesos sintéticos. A primeira e a segunda procura representam dois grupos de serviço. O código exercita o remap direto; o ponto de contagem à entrada da wave 0 consta do overlay e não foi exercitado por esta sequência. O replay K353 lê as rotas reais, sem mover os pesos reais de T1. Para o pedido natural ainda faltam um dono por conversa no manager, transições de fase autenticadas e drenagem no encerramento, barreira do último consumidor para capturas GPU e qualificação numérica no caminho do servidor. A prova não estima latência de cliente, FFN ou tráfego NAND. A paridade de gerações e componentes só cobre o percurso testado.

**Proveniência.** O C291 está pinado em `c89c88b342054223e3f27a17fbfd0954803147ac`. R01 reproduziu ambos os selos mas a fixture parou na ordem do remap, antes de medir o candidato. O pin atualiza a idade do slot por ocorrência na linha. R02 corrigiu a ordem do estímulo sintético após documentar a discrepância, preservando a política e as quatro previsões. A execução de R02 em `dd455c32419a390e363fbb6ee077b8c814993a44` demorou 7,568 s incluindo compilação. O cgroup de 1 GiB atingiu 743 555 072 B com zero swap e zero OOM. O pack sintético ocupou 79 552 512 B em Btrfs no NVMe interno. A sua verificação antes e depois corresponde a mais 159 105 024 B lidos pelo supervisor, fora das contagens de serviço dos workers. GPU e modelo tiveram zero lançamentos. [Diagnóstico preservado de R01](r02.md)

O revisor reabre as duas famílias, os logs, os dois selos e os dados de cada braço. Os caminhos R01/R02 são as raízes originais ou as cópias arquivadas. O recibo compacto reproduzível tem SHA-256 `e2ebfc4c15ba9537549195e3db3455712fe5d27a6421d111b4925e16e1b980e3`.

```sh
python3 -IB test_run.py
python3 -IB review.py --failed "$R01" --passed "$R02" --session "$FULL_PREFIX" --new-output-dir "$REVIEW_NEW"
cmp "$REVIEW_NEW/receipt.json" result.json
```

Para uma nova execução física, a partir da checkout congelada, usar o scope de CPU sem swap e dois destinos novos independentes. O supervisor autentica o compilado, os fornecedores GGML e OpenSSL e o conteúdo do pack antes de executar os braços.

```sh
systemd-run --user --scope --unit="$UNIT" -p MemoryMax=1G -p MemoryHigh=1G \
  -p MemorySwapMax=0 -p RuntimeMaxSec=100 python3 -IB "$STUDY/run.py" \
  --commit dd455c32419a390e363fbb6ee077b8c814993a44 --unit "$UNIT.scope" \
  --backend "$C291" --session "$FULL_PREFIX" --new-nvme-dir "$NEW_DATA" --new-output-dir "$NEW_RUN"
```
