# Reparação do comparador sob 256 MiB

A tentativa R01 no commit `0cc0c9ae563a02b8021cb68bb368968f02e24f8e` terminou em `FAIL_PRESERVED`. O recibo, SHA-256 `3771c9943baf920e8492b14aada3369c4b8f9ed2ebba6784bc73d071c2fd708e`, conservou uma mensagem vazia. A instrução exata que falhou nessa tentativa permanece desconhecida.

Reprodução com dados sintéticos, sem abrir os vetores históricos. No Python 3.14.10 desta estação, o arquivo de locale ocupava 233 381 888 bytes de endereçamento virtual. Com o módulo carregado, observaram-se 253 316 KiB virtuais antes de aplicar o cap. Sob 256 MiB, um recibo e uma linha sintéticos de dimensão integral falharam em `verified_row → struct.unpack` com `MemoryError`; uma chamada independente reproduziu a mesma exceção em `summarize → struct.unpack`. A mensagem de `MemoryError` foi vazia. As leituras limitadas de 1 a 3 MiB ensaiadas isoladamente passaram. A expansão em objetos Python de cada float da linha comprometia o orçamento.

O comparador percorre agora os valores F32 e os padrões binários por iteradores. Mantém a ordem de soma de `math.fsum`, o primeiro argmax em empates, a finitude, os zeros assinados e o SHA de toda a referência antes da seleção. A leitura usa o tamanho do ficheiro aberto e exige EOF nessa posição. Novos erros registam classe e localização sem paths privados. A fixture inclui a verificação pós-saída de uma linha sintética de 201 088 valores e o confronto com um ficheiro sintético integral de três linhas em processo limitado a 256 MiB.

Reabrir somente para duas execuções do protocolo original em saídas exclusivas. Os 30 s, 256 MiB, limite de saída, janela, artefactos, critérios e alcance científico mantêm-se. [Protocolo original](compact-reference.md)
