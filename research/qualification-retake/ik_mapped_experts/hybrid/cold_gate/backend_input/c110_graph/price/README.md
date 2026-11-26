# A leitura seletiva poupou 12,909 e 12,930 s no grafo frio C110

**MEDIDO · GO para o workload natural.** No portátil, o Tesy reduziu a duração somada do prefill de 16 IDs, da avaliação de um teacher e do cleanup de 24,253 para 11,344 s na ordem DIRECT→PREAD e de 24,223 para 11,293 s na inversa. Cada arranque começou com zero das 15 475 427 páginas de 4 KiB do GGUF original residentes. As 402 176 palavras F32 finitas das duas linhas coincidiram com o controlo GPU, incluindo os máximos únicos 3659 e 3992 e KV 16/17. O SHA-256 da agenda leve reproduziu o das 2 925 submissões e 72 seleções verificadas no ensaio físico anterior. [Pré-registo](protocol.md) · [Prova anterior com cópias CUDA](../README.md)

| Ordem e braço | Prefill (s) | Teacher (s) | Cleanup (s) | Total primário (s) | NVMe do cgroup em prefill / teacher (GB) | Vida do processo (s) |
|---|---:|---:|---:|---:|---:|---:|
| 1 · DIRECT | 19,288 | 4,809 | 0,156 | 24,253 | 43,966 / 9,275 | 29,486 |
| 1 · PREAD | 10,110 | 1,113 | 0,121 | 11,344 | 14,531 / 1,434 | 16,603 |
| 2 · PREAD | 10,083 | 1,098 | 0,112 | 11,293 | 14,535 / 1,434 | 16,361 |
| 2 · DIRECT | 19,280 | 4,786 | 0,156 | 24,223 | 44,006 / 9,311 | 28,884 |

As reduções DIRECT menos PREAD foram 9 177,794/9 197,169 ms no prefill, 3 695,925/3 688,149 ms no teacher e 35,188/44,588 ms no cleanup. A margem para outro custo adicional por execução é **inferior a 12 908,907 ms** para conservar os dois sinais positivos. A taxa de ganho no total foi de 53,2% e 53,4%. Os dois braços serviram sempre 14 752 627 200 B de matrizes RAM→GPU no prefill e 1 692 057 600 B no teacher. O tráfego NVMe foi medido no cgroup, com o namespace completo e os intervalos do monitor guardados à parte. [Dados por braço em bytes e ns](result.json)

O relógio de cada forward inclui `llama_decode` e a sincronização de conclusão. O cleanup inclui o drain final e a libertação das bibliotecas do modelo. Os quatro processos fizeram o mesmo trabalho, no mesmo binário, com callback e journal CUDART desligados. Ambos os braços tocam 648 155 136 B de scratch e pagam essa preparação no prefill. A alternativa muda a origem do mesmo SET de uma vista mmap para uma fatia por pread num fd independente com FADV_RANDOM. O cgroup E10 limitou cada família a 10 GiB e zero swap. Os quatro picos amostrados de VRAM foram 6 198 MiB, com 2 MiB em cada saída. A janela C55 registou AC em performance e driver 620.73.04. Cada C118 teve 61 observações. Foram quatro arranques, oito forwards, zero HTTP e zero downloads. Energia integrada desconhecida.

O C110 mede um arranque frio e dois cortes fornecidos. O servidor da conversa real já tem um primeiro turno em memória, processa 5+148 posições incrementais e faz dezenas de avaliações de decode. A recuperação de 12,9 s pertence ao C110. A melhor receita de produto verificada continua em 18,313 s até à primeira peça e 5,361 tok/s. O próximo teste verifica a capacidade do leitor nas tiles maiores e o custo do serviço no histórico natural. [Conversa nominal e ordens emparelhadas](../../../../../../packed_nvme_manifest/server_profile/conversation/ordens.md)

## Reprodução

Commit da execução `419f01944fa9a9c024d36e2b0ffe26efcc489795`, protocolo `8f9d778c`. A reabertura dos originais e a do lote privado deram o mesmo JSON byte a byte. O lote contém a compilação, o C55, a preparação e os quatro braços. Os manifestos públicos autenticam os raws privados. [Manifesto 154](../../../../../../private_archive/part-154.json) · [C110 de referência, lote 153](../../../../../../private_archive/part-153.json)

```sh
python3 -IB review.py \
  --family "$ARCHIVE/part-154/tesy-ik-e10-price-20261126-r01" \
  --family-sha256 d2c3efbfb2dc942f070f47dca71c8c23dd59a11ce4c7a2a59ff5c3547791d3e2 \
  --numerical "$ARCHIVE/part-153/tesy-ik-e10-input-20261126-r03" \
  --new-output-dir "$NOVO"
```
