# L2 de 378 entradas com entrega CPU sem SET

**NO_GO para atingir seis passos fornecidos por segundo nos dois casos no regime C294/C295.** Na escala mais favorável de serviço, o código continua 1,158 e 1,187 s acima do orçamento de 5,333333 s, mesmo dando tempo zero a todos os SET e ao intervalo residual dos workers CPU. No nominal, a mesma cache com SET CPU gratuito admite passar apenas a 0,8×, com folga de 100,8 e 41,4 ms antes dos custos de materialização, cópia, coordenação e seleção causal. Na escala observada, nem o nominal passa. R0 mantém M3 PARTIAL e M4 NOT_MET. [Protocolo](protocol.md) · [Controlo anterior](../l2_decode_entry/README.md) · [Recibo dos quatro braços](evidence/receipt.json)

Os resultados abaixo são TRACE_DERIVED/SIMULADOS. Cada braço conserva os 32 passos, os 1 152 grupos camada×passo, o estado primário, as rotas e a ordem das barreiras. A L2 conhece o futuro e escolhe até 378 chaves entre quaisquer experts à entrada I. A cada hit dá-se leitura do NVMe gratuita. A seleção foi reotimizada por cenário. Em todos, os ótimos também cabem no testemunho finito (pico de 378, zero intervalos de repetição descartados e zero referências L2 no fim). O tempo corresponde ao trabalho fixo mais a escala multiplicada pela soma dos máximos de serviço por barreira. As três escalas multiplicam também o serviço CUDA, não representam medições de outras velocidades de armazenamento.

### Retirar os SET primários na CPU

| Braço | 0,8× (s) | 1× (s) | 1,2× (s) | Folga a 0,8× (ms) | Maior escala admissível | Hits CPU / CUDA |
|---|---:|---:|---:|---:|---:|---:|
| nominal153 2 | 5,2325 | 6,0973 | 6,9621 | 100,8 | 0,823309 | 316 / 94 |
| nominal153 3 | 5,2919 | 6,1572 | 7,0224 | 41,4 | 0,809571 | 311 / 99 |
| code153 2 | 6,4925 | 7,6613 | 8,8302 | -1159,2 | 0,601656 | 321 / 80 |
| code153 3 | 6,5222 | 7,6954 | 8,8687 | -1188,8 | 0,597351 | 322 / 79 |

### Dar também tempo zero ao residual dos trabalhadores CPU

| Braço | 0,8× (s) | 1× (s) | 1,2× (s) | Folga a 0,8× (ms) | Maior escala admissível | Hits CPU / CUDA |
|---|---:|---:|---:|---:|---:|---:|
| nominal153 2 | 5,2312 | 6,0957 | 6,9601 | 102,1 | 0,823629 | 316 / 94 |
| nominal153 3 | 5,2907 | 6,1557 | 7,0206 | 42,6 | 0,809852 | 311 / 99 |
| code153 2 | 6,4911 | 7,6595 | 8,8280 | -1157,7 | 0,601842 | 321 / 80 |
| code153 3 | 6,5208 | 7,6937 | 8,8666 | -1187,4 | 0,597528 | 322 / 79 |

### O custo que a L2 ainda teria de pagar

A dimensão do payload é 13 219 200 B por geração e o pico da cache é 4 996 857 600 B, antes de metadados e alinhamento. O trabalho primário de cada réplica contém 762/319 cargas CPU/CUDA no nominal e 927/381 em código. O cenário retira o tempo dos SET primários CPU, incidindo sobre 10 073 030 400 B no nominal e 12 254 198 400 B em código. Mantém as cópias primárias CUDA e o seu serviço, para 4 216 924 800 B e 5 036 515 200 B respetivamente. Uma carga servida da L2 ainda precisa de disponibilizar o payload correto ao primário ou consumidor. Por sentido, a soma materializada e a soma a entregar são 5 419 872 000 B para 410 hits no nominal e 5 300 899 200 B para 401 hits em código. O ensaio concede gratuitamente todo o tempo destas operações. A presença de bytes em P antes de uma origem comprovada também é concedida pelo oráculo.

| Braço, apenas SET CPU gratuito | Ingressos em P / incremento / decode | READ primários restantes CPU / CUDA | Soma dos máximos de serviço CPU / CUDA a 1× (s) |
|---|---:|---:|---:|
| nominal153 2 | 276 / 102 / 32 | 446 / 225 | 2,7532 / 1,5707 |
| nominal153 3 | 273 / 105 / 32 | 451 / 220 | 2,7799 / 1,5464 |
| code153 2 | 171 / 207 / 23 | 606 / 301 | 3,7417 / 2,1025 |
| code153 3 | 176 / 202 / 23 | 605 / 302 | 3,7515 / 2,1149 |

Atribuímos os três SET de cada geração pelos eventos P8→P9. O residual é P5→P10 menos os READ e SET da própria geração. As somas destes intervalos são worker-tempo. Para a parede, o verificador reproduziu os 12 controlos C295, os oito ótimos/testemunhos de K378 anteriores, os máximos por barreira e o simulador de quatro workers nos dois cenários. A quantidade de bytes é lógica. Não houve medição de tráfego físico, de produto nem de uma implementação combinada. O C294 lê as componentes separadas no GGUF. A C293 lê um registo contíguo e não reporta a duração dos seus SET por geração. Os segundos calculados não se aplicam ao pack.

Para reabrir a hipótese conjunta nestes workloads seria preciso alterar, por exemplo, a duração dos READ nas gerações que controlam as últimas publicações, a capacidade, ou as dependências validadas. Mesmo na relaxação do residual e com a seleção ideal, o código só chega ao limite com escala ≤0,601842 e ≤0,597528, respetivamente, sem orçamento para outra atividade de serviço nesse ponto. O resultado nominal a 0,8× apenas admite uma fixture de seleção sem informação futura e custos cobrados. [C295](../../../results/c295-activation-byte-optimistic-scenario-20261006/scenario.json) · [Gate da leitura direta](../packed_worker/README.md)

### Reprodução

Confirmações na checkout limpa 0e5eb709224ead1bb1dec6bbed3cb4c2bdab140f, árvore 8f4342aa33b5a79b88df88e07248b86130364e96. R01 terminou com código 1 ao inicializar OpenBLAS sob o limite de espaço virtual e antes da escrita do recibo do programa (0,05 s, 27 356 KiB). O supervisor preservou a falha e o diretório original vazio. Mantendo o mesmo código e limite de 768 MiB, fixámos uma thread de BLAS/OpenMP nas duas novas identidades. R02 consumiu 2,40 s e 109 928 KiB de RSS. R03 consumiu 2,31 s e 109 500 KiB. Os dois resultados são idênticos byte a byte, SHA-256 713246bc14deb2271419cea6934844997c5b13bdc7431a14c1f5045744227e2a. Zero GPU, pesos e forwards. [Falha antes da recolha](evidence/controller-r01.json) · [Código](screen.py) · [Testes](test_screen.py)

```sh
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python3 -B research/qualification-retake/joint_cpu_l2/screen.py \
  --repo "$PWD" --raw-dir "$TESY_C294_RAW" --new-output-dir "$NOVA_SAIDA"
```
