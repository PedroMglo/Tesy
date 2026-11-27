# Os zeros reais do GPT-OSS-120B libertam páginas no NVMe?

**NO_GO para construir um backend de leitura esparsa com base nestes operandos.** Nos 168 usos de experts observados, cada uma das **542 304 páginas** de 4 KiB contém pelo menos um byte de peso necessário. São ocorrências de páginas no formato do pack, calculadas admitindo uma falta fria em cada rank. O ensaio leu as ativações capturadas e executou o quantizador nativo do portátil. A cobertura de páginas foi calculada sem transferir esses 2,22 GB de pesos. [Protocolo e antecedentes](protocol.md) · [Recibo reproduzido por posição e camada](result.json)

| Unidade que o leitor poderia omitir | Payload de matrizes evitável, 168 ocorrências | Fração do payload |
|---|---:|---:|
| Página no pack atual | 0 B | 0% |
| Bloco MXFP4 inteiro | 0 B | 0% |
| Byte com ambos os nibbles dispensáveis | 2 059 200 B | 0,093% |
| Nibble individual com rearranjo gratuito | 43 430 400 B | 1,956% |
| Nibble individual e conhecimento gratuito do resultado de SwiGLU antes de gate/up | 113 047 063 B | **5,090%** |

**MEDIDO nos operandos.** As posições de decode fornecidas 189–191 tinham capturas completas de entrada e SwiGLU nas camadas CPU 0–13. Os quatro IDs efetivos por posição/camada deram 168 contribuições. O quantizador C269 e a reconstrução independente coincidiram em todos os 642 600 bytes das 210 linhas Q8_0. A linha CPU0/e28 conferiu também com os bytes efetivos de uma terceira captura. Contando a entrada partilhada uma vez por rank, 3 624 das 483 840 coordenadas eram inativas nessa entrada e 22 912 no operando de down. Os zeros estavam distribuídos pelos blocos de 32. [Referência da projeção isolada](../../qualification-retake/igpu_resident_rank/projection/rank_activation/README.md)

**FORMAL para estas máscaras e este layout.** Nas duas primeiras projeções a entrada do router/FFN determina os coeficientes necessários. A ativação resultante determina-os na terceira. O cenário mais favorável concede saber antecipadamente quais as linhas inteiras que se podem retirar das duas primeiras projeções, e só desconta entradas inativas nas linhas restantes. Até nesse cenário a melhor ocorrência poupa **9,343%** do payload, na camada 13, posição 189, rank 3. A pior poupa 2,456%. As máscaras, os metadados, a aritmética para descobrir os zeros, o rearranjo em disco e a fragmentação seriam gratuitos. No cenário de serviço proporcional ao volume, o máximo fica abaixo da redução uniforme de 26,8818% que a combinação causal anterior exigia. Esta comparação circunscreve a decisão a estas entradas de decode na CPU. A distribuição no prefill real, na RTX e noutras conversas permanece desconhecida. [Origem e hipóteses do custo de serviço](../renewal/README.md)

**Execução.** Pré-registo `6f58b45e`, execução `3af0c5d76b7b76f446b1df7244427d127a6905f2`, árvore `42e72b1a51a6eacf228ab4f4da3e6f87b69c1519`. A primeira tentativa terminou antes da quantização ao esgotar um limite de espaço de endereçamento de 256 MiB durante a carga das bibliotecas, com 24 136 KiB residentes. As duas seguintes aplicaram o mesmo orçamento à memória real do cgroup, com zero swap permitido. Levaram 0,33 / 0,28 s e até 25 856 KiB de RSS. O recibo de ambas tem SHA-256 `9d349a5b6d7f20c6f9711345f57660094a934a8854f9d8854df6d81ff1f2c35f`. A C55 anterior observou o Ryzen AI 9 HX 370, RTX 4060 Laptop de 8 188 MiB, driver 620.73.04, NVMe interno, alimentação externa e perfil performance. Máximos da janela de 61,012 s, CPU 76,5 °C, GPU 43,92 °C e NVMe 35,85 °C. A energia por execução ficou por medir. Zero arranques de modelo ou cálculo na GPU. [Falha de admissão preservada](start-failure.json)

O arquivo privado exclusivo `outputs/ready-primary-20261127-01` conserva as três comparações, duas execuções por etapa, a janela C55 e a falha. Tem 13 ficheiros com 660 910 B antes do manifesto. SHA-256 do manifesto `b099fb90257f112092e8349412cec9d02f8bb98eade8383653c61b88d4d86fcd`. Os manifestos privados originais das partes 86 e 110 também são verificados pelo programa. A suíte sem modelo exercita a junção dos nibbles, o oráculo sem contagem dupla e os cruzamentos de página por enumeração.

```sh
out=$(mktemp -d)
u=research/ready-experts/operands
systemd-run --user --scope --slice=app.slice -p MemoryHigh=256M -p MemoryMax=256M \
  -p MemorySwapMax=0 -p TasksMax=32 -p RuntimeMaxSec=30 \
  python3 -IB "$u/check.py" --archive "$TESY_ARCHIVE" --libs "$C269_LIBS" \
  --new-output-dir "$out/operands"
cmp "$out/operands/receipt.json" "$u/result.json"
```
