# Quatro referências de decode em ordem de rank

**REPRODUZIDO.** Para cada um dos 32 passos fornecidos, as quatro procuras de cada uma das 36 camadas surgem pela ordem em que o router as entregou. O verificador ligou as entradas kind 3 à identidade de rota kind 2, exigiu uma única linha e quatro IDs distintos 0–127, e conservou os ranks. No modo single-row do pin C294 a ordem da primeira utilização coincide exatamente com a ordem dos quatro ranks. A SHA é calculada sobre os 4 608 bytes uint8 por chamada, camada e rank. Os quatro ficheiros completos de 33 linhas de logits também foram conferidos por tamanho, finitude e digest. [Protocolo](protocol.md) · [Recibo](evidence-r4/receipt.json)

| Caso C294 | Braços | SHA-256 das procuras ordenadas | Grupos previstos na conversa completa | Ubatch / podas formais FFN35 |
|---|---|---|---:|---:|
| Nominal | ON2, ON3 | `62ff2da0c33e77847aaa56e4c802c2a4569fcd5f08d971b9bda04a0a4c65e17c` | 78 056 | 101 / 60 |
| Código | ON2, ON3 | `2045b1c9510432fb0f98d4941db07b3f5472ffa4e9adb0c8f45ad547089dcb2c` | 74 836 | 98 / 57 |

A geometria completa resulta de 41 chamadas com seleção da última posição, as 35 camadas iniciais em todas as posições e a camada 35 nas 41 saídas pedidas. A representação TPR1 completa requer 334 033 B e 320 439 B respetivamente. Estes números dimensionam um futuro testemunho de prefixo/incremento; as identidades históricas confirmadas aqui são apenas as 1 152 linhas de decode por braço. A troca de dois ranks, o deslocamento de uma posição e a remoção da última linha foram rejeitados em todos os braços. [Verificador](verify.py)

O consumidor pode chamar `check_witness(case, groups)`, com `case` nominal153 ou code153, fornecendo linhas na ordem nativa `(decode_call, layer, absolute_position, ordered_four_experts)`. A primeira chamada de decode vale 1. A posição absoluta começa em 2 197 ou 2 105 conforme o caso. Cada lista dos quatro experts é comparada integralmente, sem ordenar. Zero modelo ou GPU. A reprodução que passou usou 1,317 s e 46 556 KiB de RSS com teto duro adicional de 256 MiB de espaço de endereçamento, no commit `609512e921ed07d4f80be3f3a79866a6ae08222a`. Os três FAILs mantêm-se preservados. [Reparação](repair.md) · [Locale e high-water anteriores ao exec](environment.md)

```sh
LC_ALL=C python3 -B - "$TESY_C294_RAW" "$NEW_REPORT" <<'PYTHON'
import subprocess, sys
subprocess.run([sys.executable, "-B", "research/qualification-retake/warm_route_reference/verify.py",
                "--raw-dir", sys.argv[1], "--new-output-dir", sys.argv[2]], check=True)
PYTHON
```
