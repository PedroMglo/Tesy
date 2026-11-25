# Escolha causal da vítima em CPU0

**GO para o próximo gate numérico.** Num pool de 40 slots cheias, proteger a cópia em RAM dos cinco experts mais recentemente admitidos e preferir esses experts como vítimas mudou as cinco ligações físicas. Os dois braços produziram os mesmos 92 160 valores F32 do FFN, bit a bit, que a referência C266. A troca deliberada dos pesos gate de dois experts, preservando as ligações e todo o routing, alterou os 92 160 valores. [Protocolo](protocol.md) · [Recibo](evidence/receipt.json)

| MEDIDO em três processos | R0 | BACKED | MUTANT |
|---|---|---|---|
| Slots físicas para os experts 45, 49, 57, 60, 98, pela ordem indicada | 0, 4, 3, 1, 2 | 35, 39, 38, 36, 37 | 35, 39, 38, 36, 37 |
| Geração nas cinco slots após substituição | 2 | 2 | 2 |
| Pesos divergentes, de 15 consultados | 0 | 0 | 2 (gate 45/49) |
| Biases divergentes, de 15 consultados | 0 | 0 | 0 |
| F32 divergentes da referência, de 92 160 | 0 | 0 | 92 160, todos finitos |

O controlo R0 nesta tabela é a escolha de vítima original no gestor C291. Em todos os braços, os mesmos quatro workers publicaram 40 experts reais, pela primeira vez na respetiva slot. O ensaio conferiu as 120 componentes desse estado e as 15 componentes copiadas para o banco de 66 096 000 B. A preferência só afeta as vítimas elegíveis. Na execução da camada, as 153 posições do router reproduziram todos os logits com e sem bias, os 612 IDs por rank e os 612 pesos. O tile nas posições [32,64) executou 24 MMID e 24 ADD_ID, com uma das oito waves ativa. Os hashes no consumidor distinguem pesos indexados pela slot física e biases indexados pelo expert lógico.

Cada filho leu do FD do pack no NVMe 594 984 960 B em 45 preads completos e entregou 594 864 000 B de pesos em 135 SET. O total de preads do pack foi 1 784 954 880 B. O cgroup registou 1 784 987 648 B de leitura de bloco para o conjunto do processo. O pico de memória foi 723 611 648 B, com zero swap e zero processos de compute GPU. A família demorou 64,16 s, incluindo 60,17 s do inventário. R01 encerrou na validação do monitor antes do primeiro filho. [Causa e correção](repair-r02.md)

O commit de protocolo é `c7c557c9`, o cliente foi construído em `f258b24b` e os três braços correram em `f024dc71`. O hash do vetor de referência é `bf0391c5e7aad2aa22c730d56c07213fadcd0db1b7801d5dd58e1533f9aaba24`. O vetor mutante é `dee7674d700ece6e862bc0c4c39f4aab31035cda4a884f96396c59add2562fa1`.

A parte privada 59 conserva o build e os dois destinos físicos, incluindo a falha pré-lançamento. O manifesto tem SHA-256 `3d224e76db01ba3d90f3886e41f2014ae86d99fe1bcc957dd9013b263bd10745`.

## Como reproduzir

Seguir o [protocolo](protocol.md) numa checkout limpa da revisão de medição. O diretório de bibliotecas contém as duas bibliotecas GGML de C269. A derivação aponta ao pack C290 pré-existente no NVMe; o programa confirma o FD aberto e o SHA de cada componente consumido.

```sh
study="$CLEAN/research/qualification-retake/packed_real_layer/policy"
python3 -IB "$study/build.py" --repo "$CLEAN" --backend "$C291" --libs "$C269_LIBS" \
  --new-output-dir "$NEW_BUILD"
systemd-run --user --scope --quiet --unit "$UNIT" \
  -p MemoryMax=4G -p MemoryHigh=4G -p MemorySwapMax=0 -p RuntimeMaxSec=850 \
  env LD_LIBRARY_PATH="$MONITOR_NVML" python3 -IB "$study/profile.py" \
  --commit "$REV" --unit "$UNIT" --build-dir "$NEW_BUILD" --build-sha256 "$BUILD_SHA" \
  --input-dir "$PREPARED_C266" --manifest-dir "$C290_DERIVED" --libs "$C269_LIBS" \
  --c55-receipt "$C55/receipt.json" --c55-sha256 "$C55_SHA" --new-output-dir "$NEW_RUN"
```

O predicado da candidata usa as tags dos backups verificados antes de consumir a rota. A seleção de um estado inicial que força um contraste dispensa reexecutar 36 camadas. Para qualificar uma política no pedido será ainda preciso verificar o estado de atenção/KV, a entrada no primeiro decode, os logits e a trajetória do target nessa agenda. O custo de manter, ler e repor o banco durante uma conversa continua a requerer comparação com controlo contemporâneo e ablação. M3 continua PARTIAL e M4 NOT_MET.
