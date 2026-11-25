# Os quatro IDs estão legíveis no GET_ROWS CPU

**PASS_CPU_READY_MARKER.** O worker zero leu a vista original de IDs no kernel GET_ROWS e obteve os 228 IDs posteriormente entregues ao primeiro remap C291. Oito threads executaram GET_ROWS em cada grafo. A CPU já continha todos os experts pedidos e o manager terminou cada remap com zero faltas. [Protocolo](protocol.md) · [Recibo compacto](receipt.json)

| Tokens | Callback C291 | IDs verificados | Cópia da vista | Fim da cópia → entrada do invólucro do remap | IDs errados com passo de 16 B |
|---:|---|---:|---:|---:|---:|
| 5 | remap simples | 20 | 70 ns | 30,448 µs | 16 |
| 20 | wave 0 | 80 | 80 ns | 55,174 µs | 76 |
| 32 | wave 0 | 128 | 110 ns | 28,494 µs | 124 |

Em cada geometria, BASE, OFF, ON e WRONG produziram os mesmos bits nos IDs compactos, nos pesos após softmax e nos slots. A contraprova manteve o cálculo do modelo e alterou apenas a leitura do observador, trocando por 16 B o passo verdadeiro de 512 B entre linhas. Restaram corretos os primeiros quatro IDs de cada amostra. Um único split CPU e os mesmos nove nós serviram os quatro braços de cada geometria. [Interposição de GET_ROWS](tap.cpp) · [Grafo e callbacks](fixture.cpp)

Cada tempo provém de uma execução ON por geometria. O último timestamp ocorre na entrada do invólucro, antes da conferência do operando e da chamada ao corpo original do remap. A janela abrange o trabalho de GET_ROWS por terminar, softmax, compactação e escalonamento. O relógio monotónico anunciou resolução de 1 ns e teve incremento positivo mínimo de 20 ns nas 1 024 diferenças de cada ON. A coluna de cópia mede o bloco delimitado pelas duas leituras de relógio. BASE e OFF só permitem validar a equivalência dos resultados e do grafo. Ficaram por medir o custo total e o intervalo interior do processo original sem observador.

O subgrafo começa em logits sintéticos e termina no primeiro remap. A [fixture mista](../packed_cpu_mixed/README.md) já observou argsort CUDA seguido de experts CPU. Para usar este marcador na conversa seria necessário provar a colocação do GET_ROWS e a disponibilidade dos IDs no host para cada reserva antecipada, e medir quanto tempo de serviço efetivamente sai da espera. A janela CPU sintética não determina a duração desse intervalo no pedido, a percentagem de esperas eliminada ou a conclusão de kernels CUDA.

## Reprodução

Na checkout limpa da revisão indicada abaixo, usar os dois backends privados C269 e C291 e o diretório novo definido por `NEW`. O scope inclui a compilação e os 12 processos sintéticos. O pico medido foi 410 632 192 B e todos os contadores de eventos de memória permaneceram a zero. O primeiro acesso ao barramento de utilizador dentro da sandbox terminou antes de criar o scope ou dados. O lançamento autorizado retornou 0. [Runner e verificação](run.py) · [Contraprovas do revisor](test_review.py)

```sh
C7=/mnt/sdisk-ssd-ext/Tesy/repo/c7-native-placement-screen-20260927-1117utc/backends
W=/mnt/sdisk-ssd-ext/Tesy/repo/build/tesy-router-ready-freeze-20261125-r01
NEW=/tmp/tesy-router-ready-20261125-r01
systemd-run --user --scope --unit=tesy-router-ready-r01 \
  -p MemoryHigh=1G -p MemoryMax=1G -p MemorySwapMax=0 -p RuntimeMaxSec=180 \
  /usr/bin/env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -IB \
  "$W/research/qualification-retake/router_ready_probe/run.py" \
  --c269 "$C7/c269-layer-last-use" --c291 "$C7/c291-expert-store" \
  --unit tesy-router-ready-r01 --commit 2acbe46173ddb0e58a3b01b88f6c305acde061ec \
  --new-output-dir "$NEW"
```
