# Restauração por alias com quatro workers C291

**MEDIDO no portátil, GO para uma prova numérica de camada CPU.** O slot 0 começou com A na geração 1. O manager reservou B na geração 2 enquanto dois leitores de A mantinham os dados vivos. Quatro workers reclamaram quatro reservas simultaneamente. Os outros três puderam publicar e o endereço de A manteve o conteúdo correto até à saída do último leitor. A reposição de A na geração 3 recuperou o inode original no mesmo endereço. O comparador verificou cada byte das três componentes nas vistas MXFP4 2880² × 40 de GGML. [Protocolo congelado](protocol.md) · [Recibo compacto](evidence/receipt.json)

| Braço | Leituras da origem | Bytes devolvidos | Bytes únicos após B | Bytes únicos após reposição de A |
|---|---:|---:|---:|---:|
| Alias | 5 | 66 109 440 | 66 109 440 | 52 887 552 |
| Sem banco | 6 | 79 331 328 | 52 887 552 | 52 887 552 |

A captura guardou uma referência ao backing, sem copiar o payload. Enquanto B ocupava o slot, reter A custou **13 221 888 B adicionais**, medidos por blocos alocados no memfd. Ao regressar ao primário, A e a sua entrada no banco partilharam esses 13 221 888 B. Essa interseção evita uma segunda materialização relativamente a um banco que conserva uma cópia separada. A ablação sem banco já ocupa a mesma memória final e precisa de reler A. Cada registo contém 13 219 200 B de pesos e 2 688 B de padding. As contagens de backing excluem tabelas de página, metadados e os quatro buffers de staging do C291.

O mutante trocou as páginas antes da libertação e os dois leitores detetaram B quando esperavam A. Uma tentativa de aquisição durante LOADING e uma devolução com geração incorreta foram recusadas nos braços de concorrência. Uma pread encurtada em 4 096 B e uma conclusão tornada obsoleta ativaram o erro persistente em processos distintos. Ambas mantiveram A instalado no endereço, sem publicação da tentativa. O destrutor fez join da equipa nos cinco braços.

A FIFO, os claims, a seleção de vítima elegível, a geração, a validação da conclusão e a publicação são do C291. A fixture prescreve o slot elegível, substitui o serviço por uma origem sintética em memfd, insere a espera pelo último leitor e remapeia o backing sob o mutex de publicação. Os leitores são threads coordenadas que percorrem os tensores. A prova anterior exercitou a matemática GGML e o scheduler misto. A cobertura de todos os consumidores da conversa e o ganho de latência requerem medição própria. [Observação mista](../mixed/README.md)

## Reprodução

Congelamentos de protocolo e implementação em `dc6dac73` e `43ec9d18`. A família durou 5,019 s incluindo compilação, com pico global do scope de 378 454 016 B, swap zero e nenhum evento OOM. O pico RSS da compilação foi 366 652 KiB. O maior pico RSS de um braço foi 134 280 KiB. O SHA-256 do recibo privado é `d65015539a31b6781315d1bab6279274ba191061752b52ba0b90ddb73b770afe`.

```sh
systemd-run --user --scope --quiet --unit="$UNIT" -p MemoryMax=1G \
  -p MemorySwapMax=0 -p RuntimeMaxSec=615 python3 -IB "$STUDY/run.py" \
  --unit "$UNIT.scope" --head 43ec9d18c6557aec19b8ce294be08618bab3eec3 \
  --backend "$TESY_C7/backends/c291-expert-store" --new-output-dir "$NEW"
```
