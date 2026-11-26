# O leitor nativo conservou o serviço e os logits do GPT-OSS-120B

**MEDIDO · GO_SERVER_CONVERSATION_GATE.** O cliente C110 original carregou a mesma biblioteca que passou no GGUF pequeno. No portátil, ambos os braços reproduziram os 597 quartetos ordenados e os 402 176 valores F32 finitos do controlo ik GPU independente. Cada um executou as mesmas 2 925 cópias CUDART dos pesos originais para as posições físicas da cache. As vistas do modelo, do scratch e dos fornecedores em memória foram confrontadas com os dois cortes e com o journal de R03. [Protocolo](protocol.md) · [Dados por fase](result.json)

| Origem de cada cópia | Barreiras de IDs | Esperas por pressão | Payload prefill / teacher | NVMe do namespace, vida do processo | Pico e saída da RTX |
|---|---:|---:|---:|---:|---:|
| Vista mmap do GGUF | 72 | 0 | 14,753 / 1,692 GB | 35,948 GB | 6 198 / 2 MiB |
| Pread no scratch limitado | 72 | 0 | 14,753 / 1,692 GB | 8,921 GB | 6 198 / 2 MiB |

Mantiveram-se ctx8192, ub32, 288 slots ClassLRU, os mesmos 16 IDs de entrada e o teacher 976. Seis SETs pertenciam à última geração. A série chegou ao cleanup com o stream vivo e libertou a RTX em ambos os braços. A capacidade e o pico lógico de scratch foram 648 155 136 B. Cada braço teve 61 amostras C118, E10 e zero swap. As vidas dos processos foram 20,303 e 10,565 s. Os relógios desta ordem com journal e estado de cache distinto são diagnósticos. O preço do mecanismo com o mesmo trabalho, cache fria e ordens invertidas foi medido separadamente. [Comparação emparelhada](../../../c110_graph/price/README.md)

Os máximos únicos 3659/3992 coincidiram com C110, stock e ik CPU. Face ao stock, o máximo absoluto da diferença numérica foi 0,620224 no prefill e 1,040717 no teacher. Face ao ik CPU foi 2,504238/1,033109. O contrato de igualdade bit a bit foi satisfeito contra o controlo ik GPU para ambas as linhas completas. O custo da nova cache e as próximas emissões naturais serão avaliados no servidor que consome o próprio histórico. A qualificação de M3/M4 continua em aberto.

A árvore da execução foi congelada no commit `95a6347378191a1d479216a0a3325c21b04305f3`. Quatro forwards, dois arranques, zero HTTP e zero downloads. A energia integrada permanece desconhecida. O revisor produziu os mesmos bytes nos originais e no arquivo privado. [Manifesto 158](../../../../../../../private_archive/part-158.json) · [Execução, falhas e C55 do gate pequeno](../README.md)

```sh
python3 -IB review.py --family "$FAMILIA" \
  --family-sha256 ff5870866e0426efb86b8bde4ae9ef52f8f3a8dda8c532ffecd6f9caa2e84a97 \
  --previous "$SYS73" --model "$GGUF_NVME" --plan "$PLAN" --numerical "$R03" \
  --c110-parent "$C110" --stock-file "$STOCK" --cpu-d0 "$CPU0" --cpu-d1 "$CPU1" \
  --new-output-dir "$NOVO"
```
