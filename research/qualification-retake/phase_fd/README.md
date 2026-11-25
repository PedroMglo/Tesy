# Bytes devolvidos pelo descritor de experts

**PASS na fixture C269 sem modelo.** Um retorno com A em curso continha 8 192 B lidos. B pôde publicar enquanto A continuava à espera. Nesse instante o mesmo FD acumulava 16 736 B. A completou a terceira componente e o total passou a 17 088 B. Logo, um contador do FD amostrado no retorno e uma soma por chamada de origem podem dar valores diferentes, mesmo com todos os bytes e destinos corretos. [Protocolo](protocol.md) · [Recibo](evidence/receipt.json)

| Caso, reproduzido com OFF e ON | Chamadas pread no FD | B pedidos | B devolvidos | B aplicados com SET | Gerações publicadas |
|---|---:|---:|---:|---:|---:|
| EOF após o payload necessário | 6 | 24 576 | 17 088 | 768 | 2 |
| EOF um byte antes de completar a última componente | 3 | 12 288 | 8 415 | 256 | 0 |

Cada geração pediu três páginas de 4 096 B para três slabs de 128 B. A última leitura válida devolveu 352 B. No caso inválido devolveu 223 B e a geração precisava de 224 B para vencer o desalinhamento e incluir o slab. O worker preservou os dois SET já concluídos e assinalou falha antes de publicar a slot. Uma entrada obsoleta e uma duplicada permaneceram sem leitura adicional. O controlo independente confirmou o conteúdo dos destinos e excluiu uma leitura de outro descritor. Os quatro workers terminaram em cada braço. [Fixture](fixture.cpp) · [Observador](observe.h)

**Alcance.** O executável OFF usa o fonte C269 intacto. O ON observa a resposta real de pread e as componentes/generações no worker do mesmo pin. A fixture usa um ficheiro anónimo, ativa o ramo de cálculo de intervalos alinhados e controla as submissões A/B. O retorno é uma fronteira do controlador, com pendências verificadas sob o mutex. O ensaio não cronometrou a conversa, não mediu tráfego de dispositivo e não propagou a origem através do scheduler assíncrono real. No C269, o retorno de `llama_decode` por si só não prova que o último serviço terminou. [Observabilidade do C269](../prefill_read_floor/observability.md)

O C135 já reconcilia 135 leituras para a chamada de 5 e 3 531 para a de 148. A 4 406 400 B de payload por componente, correspondem a 594 864 000 e 15 558 998 400 B respetivamente. O campo do journal é `wt.nb_expert`. Os recibos antigos conservam esse resultado lógico; o syscall pode devolver bytes de alinhamento ou uma leitura curta válida. Só uma pergunta que dependa especificamente da distribuição contemporânea desses bytes justifica o próximo gate. Seria necessário vincular cada reserva à chamada/grafo original e observar a entrada, o retorno e as pendências sem introduzir um drain. A neutralidade OFF/ON, incluindo o custo do observador nas fases, permanece por medir. [Contas do C135](../prefill_read_floor/README.md) · [Emissor C122](../../../patches/C122-warm153-decode-trace.patch)

**Reprodução.** Protocolo `dad43a64`, código `c1de0a3d7db0ae36e89f86fad847184045cc31e3`, C269 `d0ebfbcc6c8f456bc1083027c1b08075a32824d8`. A compilação e os quatro braços ocuparam 2,382 s no controlador. O cgroup registou 165 298 176 B de pico, zero eventos de máximo/OOM e zero swap. A saída privada ocupou 2 528 107 B. O SHA-256 do recibo é `c19eb46347626c80d402ef4d406c394f4e3458fc61ff10dca40c7cf7aca68aca`. Nenhum forward ou utilização de GPU.

```sh
systemd-run --user --pipe --wait --collect --unit=tesy-phase-fd-replay-01 \
  -p Type=exec -p MemoryMax=512M -p MemorySwapMax=0 -p RuntimeMaxSec=120s \
  -p TimeoutStopSec=2s -p TasksMax=24 \
  /usr/bin/python3 -B "$W/research/qualification-retake/phase_fd/run.py" \
  --backend "$TESY_C7/backends/c269-layer-last-use" \
  --expect-head c1de0a3d7db0ae36e89f86fad847184045cc31e3 --new-output-dir "$NEW_DIR"
```
