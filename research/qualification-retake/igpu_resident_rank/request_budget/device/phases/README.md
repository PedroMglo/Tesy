# Leituras por fase do mesmo pedido com o pack integral

**Durante o prefill dos 153 tokens novos de T2, o cgroup do servidor submeteu pelo menos 16 437 952 512 bytes de leitura ao namespace NVMe.** No decode das 47 saídas, o mínimo foi 14 279 639 040 bytes. Um rank que acelere apenas o decode mantém o trabalho de leitura observado no prefill se o percurso deste permanecer igual. Os contadores abrangem o scope inteiro e o tempo das transferências pode sobrepor-se ao cálculo. Esta reanálise não estabelece uma duração de I/O irredutível.

| Turno e fase | Tempo nativo | Amostras interiores | Bytes de leitura submetidos pelo cgroup [mín., máx.] | BIOs de leitura do cgroup [mín., máx.] | Setores de leitura de 512 B concluídos pelo namespace [mín., máx.] |
|---|---:|---:|---:|---:|---:|
| T2 prompt, 153 tokens | 9,553552 s | 95 | 16 437 952 512 – 16 752 132 096 | 125 571 – 127 990 | 32 123 008 – 32 718 336 |
| T2 decode, 47 saídas | 8,784071 s | 88 | 14 279 639 040 – 14 580 596 736 | 109 116 – 111 434 | 27 890 768 – 28 484 048 |
| T1 prompt, 2043 tokens | 57,981506 s | 580 | 45 055 012 864 – 45 359 116 288 | 344 500 – 346 825 | 88 109 688 – 88 663 000 |
| T1 decode, 78 saídas | 17,659631 s | 176 | 30 238 490 624 – 30 529 372 160 | 231 052 – 233 276 | 59 082 648 – 59 742 040 |

O arquivo contém 988 amostras do mesmo processo, inode de cgroup e namespace. O resultado SSE final fornece os tempos de prompt e decode do próprio turno. A diferença entre a janela HTTP e a soma desses dois tempos foi 12,130608 ms em T2 e 12,093561 ms em T1. Sob a premissa de fases ordenadas e sem sobreposição, o verificador admite que todo esse residual ocorra antes, entre ou depois das fases. Para o mínimo, usa exclusivamente duas observações inteiras dentro da fase em todas as colocações admissíveis. Para o máximo, usa duas observações exteriores a todas elas. Cada corte inclui a margem de 2 µs e a largura real de leitura dos contadores. As maiores lacunas nas duas fases de T2 ficaram abaixo de 102 ms. Os setores incluem atividade de outros cgroups. [Critério exploratório](protocol.md) · [Recibo completo com limites em bytes e setores](receipt.json)

A pergunta por fase foi definida **depois de medido o braço P** e antes da abertura destas contagens. O pré-registo secundário é `d8bae32f`. O verificador reabriu os 49 ficheiros da parte 88 e reproduziu a graduação anterior. O novo recibo tem SHA-256 `c61f26fa85bb27dd2e7b20c36ebd939f189aab9955381f7382d6e12fe24fe574`. Não houve novo pedido ao modelo. [Observação original](../README.md) · [Manifesto da parte 88](../archive-88.json)

```sh
D=research/qualification-retake/igpu_resident_rank/request_budget/device/phases
python3 -IB "$D/test_screen.py"
python3 -IB "$D/screen.py" --archive "$TESY_PRIVATE_ARCHIVE" --new-output-dir "$NEW_RESULT"
```
