# Plano de leitura até ao primeiro conteúdo final

**REPRODUZIDO.** O pedido nominal T2 da conversa C281 com PFJ1 ligado tem 875 primeiras admissões obrigatórias no recorte pré-registado. Houve 2 625 leituras completas em 441 grupos de procura. Em 288 grupos havia um único trabalho elegível. Os maiores dois grupos tinham dez. A reconstrução confirmou a ordem de entrada na fila dentro de cada grupo, a geração e os três intervalos por expert no inventário GGUF independente. As duas preparações emitiram o mesmo plano privado de 187 413 B, SHA-256 `196e94e9b3c267d0821edfe57ddd7508c6ea3380e72b46a11570c33f753723e2`. [Protocolo](protocol.md) · [Recibo da confirmação](plan-r02/receipt.json)

| Grandeza | Por travessia |
|---|---:|
| Payload MXFP4 | 11 566 800 000 B |
| Bytes pedidos por O_DIRECT com alinhamento de 4 KiB | 11 577 561 088 B |
| Maior pedido individual | 4 411 392 B |
| Reserva máxima para verificar todos os payloads depois da barreira | 132 341 760 B |
| Piso com os tempos READ do journal para os quatro workers | 6,231568365 s |
| Tempo conservado fora das callbacks até ao primeiro conteúdo final | 5,996895714 s |
| Orçamento para estes grupos no alvo de 10 s | 4,003104286 s |

O orçamento exige 2,89215 GB/s de bytes alinhados agregados sobre a **soma dos makespans dos grupos**, incluindo o despacho e a última barreira. Um valor de leitura sequencial isolada do SSD responde a outra pergunta. O teto condicional para o serviço observado no journal é 64,2391% do piso histórico. O teste de disco concede gratuitamente os restantes trabalhos das callbacks, as cópias aos destinos e o cálculo concorrente. A medição de produto e a decisão sobre uma política causal exigem o pedido completo. [Origem do relógio e do recorte](../mandatory.md)

Para reproduzir com os artefactos privados autorizados, indicar a raiz da conversa OFF R01 e ON R02 por `OFF` e `ON`, o arquivo C281 de referência por `HIST`, o inventário GGUF C7 por `INVENTORY`, o manifesto da part-37 por `MANIFEST` e um diretório novo por `DEST`.

```sh
python3 -IB research/qualification-retake/phase_fd/integrated/cold_read_fixture/test_plan.py
python3 -IB research/qualification-retake/phase_fd/integrated/cold_read_fixture/plan.py \
  --on-dir "$ON" --off-dir "$OFF" --historical "$HIST" \
  --inventory "$INVENTORY" --archive-manifest "$MANIFEST" --new-output-dir "$DEST"
```

O protocolo foi congelado em `d73a6542`. A preparação inicial levou 0,28 s e atingiu 54 536 KiB de RSS. A confirmação na checkout limpa `007056b5a76b7032b196a34ecc14c12cb875aab9` levou 0,29 s e atingiu 56 504 KiB. A preparação usou exclusivamente recibos, journal e metadados, com zero bytes de pesos e zero forwards. As duas travessias físicas propostas requisitam juntas 23 155 122 176 B. O cgroup admitido para cada uma tem 256 MiB, stop a 224 MiB, swap zero. A reserva de 132 341 760 B e a provisão de 64 MiB para o processo cabem nesse stop.
