# Um motor independente reproduz um expert escolhido pelo 120B?

A entrega das primeiras linhas ao kernel atual foi ensaiada em seguida com quatro leitores e os quatro experts da rota. [Leitura parcial, ablação e join](delivery.md)

**MEDIDO · NO_GO como substituto bit a bit do operador CPU observado neste portátil.** No primeiro rank do primeiro decode capturado à posição 189, o target escolheu o expert 28 da camada 0, slot 3 e geração 6. Ao corrigir a ordem dos pesos, ambas as compilações do executor independente ainda divergiram em **8 640 de 8 640** resultados pré-bias. Converter também as ativações para a representação Q8_0 do target baixou substancialmente o erro e deixou **7 189 de 8 640** resultados com bits diferentes. [Protocolo](protocol.md) · [Resultados e hashes por projeção](result.json)

| Projeção | Saídas | Diferentes após corrigir a ordem | Erro absoluto máximo | Diferentes aplicando também Q8_0 | Erro absoluto máximo |
|---|---:|---:|---:|---:|---:|
| Gate | 2 880 | 2 880 | 0,010401 | 2 344 | 0,000003100 |
| Up | 2 880 | 2 880 | 0,022682 | 2 333 | 0,000005484 |
| Down | 2 880 | 2 880 | 0,059629 | 2 512 | 0,000020981 |

Os três produtos registados do C269 reproduziram todos os bits das saídas gravadas numa execução independente do modelo. As entradas gate/up vieram da normalização da atenção capturada noutro processo. Down recebeu a ativação SwiGLU autêntica, também idêntica nas duas capturas. Assim, o erro de gate/up fica fora da medição do erro de down. O quantizador reconstruído em aritmética independente coincidiu nos três buffers Q8_0. Duas compilações, escalar e AVX2, produziram as mesmas contagens. O contraexemplo anterior com duas ativações construídas já distinguia o contrato F32 do contrato Q8_0 em 2 170 de 2 880 linhas de outro expert. [Contraexemplo controlado](../activation/README.md) · [Referência por rank](../../../operands/README.md) · [Código independente estudado](https://github.com/FiveTechSoft/gpt-oss-120b/blob/9570410cab7e34bf7ac044559fc56dcdf4c7c195/engine/src/dequant.c)

Estes dados localizam uma diferença real de operador. O efeito na qualidade da linguagem, no argmax e na velocidade do motor independente continua por medir. A prova seguinte para um novo executor pode reutilizar o kernel comprovado, implementar a ordem numérica da referência ou estabelecer prospectivamente outra tolerância apropriada e verificar logits, trajetória e produto. A decisão económica de construir o executor exige ainda um ganho em trabalho crítico que pague as suas novas fronteiras.

No commit `6eebdf372ecf6a04865f2a9aaf50133c29050950`, dois processos CPU leram cada um 13 219 200 B lógicos dos três componentes originais, sem forward do modelo ou acesso à GPU. Duraram 0,195 / 0,165 s, com pico máximo do cgroup de 75 362 304 B, cap de 512 MiB e zero swap. Os recibos são idênticos, SHA-256 `35d6cb4e37fc49c903d66654f9578ed98a9365484026e678a1ca0d453a9c661d`. O arquivo preserva os originais e ambas as proveniências. [Comandos](commands.json) · [Arquivo](archive.json)
