# O backend limitado conservou cada cópia e os logits na RTX

**MEDIDO · GO_NATIVE_C110.** A cache do ik usou o leitor do Tesy com o cliente BANK9 original. A RTX recebeu 24 cópias das três matrizes de experts por braço. Em DIRECT os ponteiros vieram das vistas corretas do GGUF. Em PREAD_RANDOM vieram do mesmo buffer anónimo de 262 144 B. Os dois braços fizeram as quatro esperas adicionais previstas antes de reutilizar esse espaço. Os 66 quartetos ordenados e as 1 056 palavras F32 finitas de prefill e primeiro decode coincidiram bit a bit com o controlo residente independente. [Protocolo](protocol.md) · [Resultado reaberto](result.json)

| Biblioteca e origem | Operações consumidoras | Cópias auditadas pelo hook | Esperas adicionais | Pico RTX |
|---|---:|---:|---:|---:|
| Original BANK9 | 24 | — | — | 130 MiB |
| Candidata DIRECT | 24 | 24 | 4 | 130 MiB |
| Candidata PREAD_RANDOM | 24 | 24 | 4 | 130 MiB |

Cada braço foi um processo com a biblioteca identificada nos seus mapas. A geração, a gama do ficheiro e a posição do slot de cada submissão foram reconciliadas com o controlo anterior e com a respetiva chamada CUDART. Os 101 objetos originais voltaram a produzir a biblioteca original byte a byte. Substituir o único objeto de cache e repetir o link deu duas vezes o SHA-256 `fcfc79ddf7c8ce208bcd9f3bbf19f19c1edd76311f09e457679d9be06a2c4544`. O código stock fica no pin `7a5d90009b7ae55d3239cdd33244977c4eb10ff6`. [Alteração no backend](cache.patch) · [Proprietário por contexto](native_input.hpp)

A compilação demorou 3,012 s e gerou 14 215 842 B. O C55 teve SHA `a0c87541ee152e6fa561aa00a6457b1d184d943a95dca7b5a35c7ea8bd062142`. A preparação R01 recebeu o cliente arquivado de outra build e terminou por divergência do hash antes de arrancar um modelo. R02 usou o cliente autenticado do controlo. O commit físico foi `47d093b2db1b6d98c243e7cd5333848eaa334a40`, com três arranques, seis forwards do GGUF pequeno, 533 794 816 B de pico no cgroup, zero swap e zero HTTP. Energia desconhecida. O lote 157 inclui as duas preparações, build, janela e família física. O resultado compacto coincidiu nos originais e no arquivo. [Manifesto e contagem de bytes](../../../../../../private_archive/part-157.json)

A decisão abre o mesmo hook nos dois cortes C110 do GPT-OSS-120B do NVMe interno. A redução anterior de 12,91–12,93 s refere-se aos dois cortes frios da implementação de investigação. Para M3/M4 conta a resposta natural ao segundo turno, construída com o histórico do primeiro. [Medição C110](../../c110_graph/price/README.md) · [Conversa nominal](../../../../../../packed_nvme_manifest/server_profile/conversation/ordens.md)

```sh
python3 -IB review.py --family "$FAMILIA" \
  --family-sha256 18d5cbce12d961fcae705735a9caec861b00785dcd2c5e09cb478838a68309e5 \
  --graph "$ARCHIVE/part-150/tesy-ik-graph-input-20261126-r01" \
  --historical "$BANKS_SYS73" --tiny "$TINY_GGUF" --new-output-dir "$NOVO"
```
