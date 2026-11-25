# Separar as três leituras de cada falta num pool de quatro workers

**NO_GO para atingir 6 tok/s nos dois casos C294 através desta mudança isolada, às durações de serviço estudadas.** O piso para as leituras isoladas cabe nos quatro braços. Ao repor o trabalho fixo do próprio decode, o candidato mais favorável ainda precisa de **5,604–5,620 s no nominal** e **6,382–6,404 s em código** para 32 passos. O limite é 32/6 = 5,333333… s. Mesmo cobrando só 80% da duração dos READ, o código excede o limite em 135–156 ms. A janela nominal passaria a dispor de 471–496 ms para todos os custos omitidos.

## Quatro braços

Todas as durações estão em segundos. R0 foi observado no journal entre o início do primeiro decode e o fim do 32.º. O controlo serial e o candidato paralelo são pisos condicionais do mesmo braço. No controlo, cada worker lê os três componentes consecutivos de uma geração. O candidato distribui componentes independentes pelos mesmos quatro workers e só atravessa a barreira após completar todas as gerações desse grupo. A última coluna é a duração do trabalho fixo com o qual se avaliam ambas as agendas. [Protocolo](protocol.md) · [Recibo completo](evidence/receipt.json)

| Braço trace ON | R0 observado | Só READ serial | Só READ paralelo | Diferença entre os pisos | Resto fixo |
|---|---:|---:|---:|---:|---:|
| nominal 2 | 9,381482 | 7,070178 | 3,830251 | 3,239927 | 1,773408 |
| nominal 3 | 9,414981 | 7,037752 | 3,789025 | 3,248727 | 1,830919 |
| código 2 | 10,986137 | 8,510768 | 4,564396 | 3,946372 | 1,817114 |
| código 3 | 11,009780 | 8,507797 | 4,575133 | 3,932664 | 1,829011 |

A margem abaixo é positiva quando há orçamento para coordenação, SET, publicação e contenção adicionais. Uma margem negativa quantifica o corte que ainda falta, mesmo atribuindo zero a esses custos. O fator máximo multiplica apenas a duração das leituras, preservando o restante fixo e assumindo custo adicional zero.

| Braço | Serial + fixo a 1× | Paralelo + fixo a 1× | Margem 1× | Paralelo + fixo a 0,8× | Margem 0,8× | Fator máximo |
|---|---:|---:|---:|---:|---:|---:|
| nominal 2 | 8,843586 | 5,603659 | −0,270326 | 4,837609 | +0,495725 | 0,92942 |
| nominal 3 | 8,868671 | 5,619944 | −0,286611 | 4,862139 | +0,471194 | 0,92436 |
| código 2 | 10,327882 | 6,381510 | −1,048177 | 5,468631 | −0,135297 | 0,77036 |
| código 3 | 10,336808 | 6,404144 | −1,070811 | 5,489117 | −0,155784 | 0,76595 |

**TRACE_DERIVED.** Para cada braço, o verificador reproduziu o recibo do controlo serial, os hashes das 1 152 rotas e das âncoras I, a identidade de cada geração e o relógio C295. Cada READ recebe até 1 µs de desconto pela resolução do journal. Para cada grupo com até 12 READ indivisíveis, o algoritmo começa por uma atribuição viável e examina todos os ramos que ainda podem melhorá-la. Permutações de workers com cargas iguais são equivalentes. O maior READ e um quarto do trabalho total arredondado por excesso fornecem um limite inferior. A atribuição preserva todos os componentes e o hash por braço cobre as quatro listas de tarefas de cada grupo. Os testes comparam o resultado com uma enumeração independente e incluem um caso em que a atribuição inicial é subótima. [Implementação](screen.py) · [Testes](test_screen.py)

A soma dos máximos dos grupos usa as dependências observadas entre camadas e passos. A união observada dos READ fora da espera P11–P12 é zero nos quatro braços. A cauda após a última barreira, incluída no restante fixo, foi 3 738 / 3 741 µs no nominal e 3 448 / 3 417 µs em código. O cenário conserva os misses do R0, incluindo cada recarga do mesmo expert de uma camada num passo posterior. O NVMe teria de sustentar as novas leituras concorrentes com as durações admitidas. Os journals do controlo não observam essa condição.

## Cardinalidade e payload

| Caso | Grupos por 0 / 1 / 2 / 3 / 4 faltas | Cargas CPU / CUDA | READs | Payload lógico | Débito para 32/6 s, só serviço | Débito com resto fixo, braços 2 / 3 |
|---|---|---|---:|---:|---:|---:|
| nominal | 469 / 402 / 185 / 75 / 21 | 762 / 319 | 3 243 | 14 289 955 200 B | 2,67937 GB/s | 4,01412 / 4,08003 GB/s |
| código | 333 / 447 / 267 / 93 / 12 | 927 / 381 | 3 924 | 17 290 713 600 B | 3,24201 GB/s | 4,91742 / 4,93411 GB/s |

Cada READ transporta 4 406 400 B de payload. O débito requerido divide esse payload pelo intervalo disponível às leituras, em GB decimais. Os contadores físicos do dispositivo e os efeitos de alinhamento, cache e inflight permanecem por medir para a agenda paralela. Nos grupos de uma única falta, a redução do piso de serviço é 1,798 / 1,793 s no nominal e 1,979 / 1,981 s em código. Nos grupos com duas a quatro faltas é 1,442 / 1,456 s e 1,967 / 1,952 s, respetivamente. A repartição completa por tier e cardinalidade está no recibo.

## Antecedente e condição de reabertura

**MEDIDO em C125B.** O teste O_DIRECT com offsets reais comparou quatro workers de experts e doze de componentes, em 1 012 grupos C123 com 1 509 cargas e 19 947 772 800 B por braço. Os dois pares pioraram 2,352% e 1,223%. A mediana de −1,787% ficou abaixo do gate de +15%. C125B incluía submissão Python e a barreira real. Aqui o pool mantém quatro workers, os grupos são C294 e todos os custos de divisão e junção são dispensados. O resultado físico anterior e o crivo presente fornecem razões independentes para encerrar a promoção desta variante. [Resultado C125B](../../C125B-COMPONENT-IO-RESULT-20260929.md) · [Protocolo para isolar os grupos de uma só falta no antecedente](../c125_singleton/protocol.md)

Uma reabertura requer uma premissa mensurável que mude o custo ou o trabalho do mesmo grupo. O teste físico mínimo compararia agendas seriais e por componentes, com quatro workers nos dois braços, offsets e bytes idênticos no armazenamento alvo e barreiras reais, separando singleton e múltiplas faltas. Teria de cobrar submissão, contenção, cópias e publicação, preservar a geração e medir o relógio da última entrega. Estas condições antecedem qualquer campanha 120B. O crivo de decode não qualificou prefill, primeiro conteúdo final, utilidade ou o objetivo operacional. M3 PARTIAL e M4 NOT_MET.

## Reprodução

Na checkout limpa `106f1bfb837e15892fedb0978abd0cc1f6ac8d68`, usar a raiz raw da C294 e um destino novo em cada processo.

```sh
OPENBLAS_NUM_THREADS=1 python3 -B research/qualification-retake/component_parallel/screen.py \
    --raw-dir "$TESY_C294_RAW" --new-output-dir "$NEW_OUTPUT"
```

R01 e R02 geraram recibos de 28 100 B idênticos, SHA-256 `cbd7ac1883b9f4a1d0d5e08d53b7b5f4eec13889622a96fca4ff8c969a064003`. R01 usou 1,31 s e 104 876 KiB de RSS máximo, R02 usou 1,30 s e 104 880 KiB. Cada processo tinha 120 s, 512 MiB de espaço virtual e 8 MiB para a saída. Esta unidade não iniciou modelo nem GPU. [Recibo das reproduções](evidence/reproductions.json)
