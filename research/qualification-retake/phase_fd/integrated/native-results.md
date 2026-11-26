# Proveniência dos pedidos de leitura no C269

**PASS nos cinco braços da fixture CPU.** O journal distingue uma leitura pendente
da primeira chamada das leituras iniciadas na segunda, mesmo quando
o trigger só admite observar a segunda chamada. A leitura do expert 127 começou na
primeira chamada e terminou depois do retorno da segunda. No braço em que
só a segunda foi capturada, a origem herdada continuou marcada como tal,
com instante inicial desconhecido. Os quatro workers terminaram em cada
braço.

| Braço | preads no FD | B pedidos | B devolvidos | Payload aplicado (B) | Publicações |
| --- | ---: | ---: | ---: | ---: | ---: |
| OFF, cauda suficiente | 120 | 516 096 | 512 096 | 15 360 | 40 |
| ON, cauda suficiente | 120 | 516 096 | 512 096 | 15 360 | 40 |
| OFF, cauda curta | 120 | 516 096 | 512 095 | 15 232 | 39 |
| ON, cauda curta | 120 | 516 096 | 512 095 | 15 232 | 39 |
| ON a partir da segunda chamada | 120 | 516 096 | 512 096 | 15 360 | 40 |

No último braço, o controlo externo conta a execução inteira. O journal
contém apenas 13 conclusões de pread, das quais uma herdada e doze da
chamada corrente. A leitura de cauda devolveu 4 192 B nos braços válidos
e 4 191 B nos braços de erro, deixando por aplicar a terceira componente
de 128 B. Cada destino foi comparado com a fórmula usada no ficheiro
sintético. Estes bytes provêm da interface pread.

O driver executou no scheduler GGML CPU as callbacks nativas de remap de
uma wave e de uma chamada de um token. Ligou diretamente o objeto de gestão
de experts do DSO candidato e reproduziu os blocos de marcação da TU de
contexto em torno de chamadas exteriores sintéticas. O C270 em E20 fica
responsável por confirmar o encadeamento num contexto autêntico, os logits
e a seleção do DSO no processo. Esta fixture não qualificou a latência da
observação, a colocação dos pesos entre CPU e CUDA ou uma conversa.

R01 falhou na verificação do formato do manifesto antes da compilação do
driver. A correção preservou a verificação do conteúdo selado e rejeitou
uma entrada alterada numa contraprova. R02 ocupou 0,788 s no controlador
e 167 014 400 B de pico de cgroup, com zero swap. Código medido
`db34bde6556a826cf46b72881b6dbc8a448580ad`; DSO candidato
`911b3be5b529d8e07409c12cf600ca9f7f6182f7a397fc6de265e5ea4be254eb`.
[Protocolo](native-fixture.md) · [Correção](native-fixture-r02.md) ·
[FAIL R01](native-r01.json) · [Recibo R02](native-r02.json)

```sh
systemd-run --user --pipe --wait --collect --unit=tesy-phase-fd-fixture-01 \
  -p Type=exec -p MemoryMax=512M -p MemorySwapMax=0 -p RuntimeMaxSec=120s \
  -p TimeoutStopSec=2s -p TasksMax=24 /usr/bin/python3 -IB \
  "$W/research/qualification-retake/phase_fd/integrated/native_fixture.py" \
  --backend "$C269" --build-dir "$BUILD_PFJ1" \
  --expect-head db34bde6556a826cf46b72881b6dbc8a448580ad \
  --new-output-dir "$NOVA"
```
