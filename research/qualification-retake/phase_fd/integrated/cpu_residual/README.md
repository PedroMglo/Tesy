# Quanto pode mudar a colocação dos oito threads de cálculo?

**NO_GO autónomo para afinidade que só encurta cálculo fora do remap e conserva a duração observada do serviço.** O portátil distingue dois grupos de núcleos e o dot MXFP4 usado pelo R0 tem taxas diferentes nos seus representantes. A C281 regista a equipa pedida, os argumentos e o ambiente. Para identificar a colocação efetiva falta uma observação que associe TID, CPU lógica e intervalo de execução à operação. O PFJ1 identifica os quatro workers do serviço por ordinal interno. Atribuir a estes ordinais uma classe de núcleo exigiria a mesma ponte com o sistema operativo. [Crivo reproduzível](screen.py) · [Valores e identidades dos ficheiros](receipt.json)

## Topologia e equipas

**MEDIDO em leitura em 25 de novembro.** O Linux mostra um nó NUMA, 12 núcleos, 24 CPUs lógicas e dois SMT por núcleo. Os limites de frequência abaixo vieram de cpuinfo_max_freq. As frequências durante o pedido variam com a carga, o orçamento térmico e a potência. A AMD especifica quatro Zen 5 e oito Zen 5c neste modelo. [Ficha do Ryzen AI 9 HX 370](https://www.amd.com/en/products/processors/laptop/ryzen/ai-300-series/amd-ryzen-ai-9-hx-370.html)

| Núcleos e irmãos SMT | L3 partilhada no Linux | Frequência máxima reportada | Classe |
|---|---:|---:|---|
| 0–3 e 12–15 | 16 MiB | 5,158 GHz | Zen 5 |
| 4–11 e 16–23 | 8 MiB | 3,289 GHz | Zen 5c |

O argv selado do servidor pós-atualização fixa `-np 1 -t 8 -tb 8 --moe-stream-io-threads 4`. O contexto C269 escolhe oito threads de cálculo para a posição única ou oito para batch. A função do backend envia o mesmo número à equipa apropriada em cada grafo. A compilação C269 tem GGML_OPENMP=ON. A região paralela confirma internamente o número obtido com omp_get_num_threads e aplica a máscara por thread apenas quando válida. O manager inicia quatro std::threads diferentes, que esperam pela fila. O controlo C281 deixa as variáveis de colocação e espera OpenMP/GOMP/KMP ausentes. A afinidade efetiva de um PID pode ainda depender do cgroup, do escalonador e de herança por thread. [Sessão C281 e binários](../../../nvme_conversation/postupdate/physical-result.md) · [Protocolo C281](../../../../../results/c281-persistent-r0-runtime-20261005/protocols/c281-r0-persistent.json)

**Fontes locais do backend** no commit C269 `d0ebfbcc6c8f456bc1083027c1b08075a32824d8`. Em `src/llama-context.cpp:2479`, graph_compute seleciona a equipa com a flag batched. Em `ggml/src/ggml-cpu/ggml-cpu.c:1528`, MUL_MAT_ID reparte a quantização da ativação, prepara as listas por expert e sincroniza. A distribuição dos blocos de linhas permite recolher mais trabalho por contador atómico. As barreiras também esperam pelos threads mais lentos. Na mesma fonte, linhas 3280 e 3348, GGML configura as máscaras por thread e entra na região OpenMP. A criação do serviço e a espera do worker estão em `src/llama-moe-stream.cpp:302` e `:323`. L3 partilhada, migrações, SMT, espera nas barreiras e contenção com o serviço podem alterar os resultados da equipa.

## Qual é a diferença já observada?

Cada célula é a mediana das duas extremidades R do ensaio anterior, uma thread fixada ao representante, com as mesmas entradas reais. As duas cópias de R no estrato quente percorreram 64 linhas 4096 vezes e as do estrato largo percorreram 23 040 linhas 12 vezes. [Braços individuais](../../../mxfp4_vnni/evidence/arms.tsv)

| Região | CPU0, Zen 5 | CPU4, Zen 5c | Taxa CPU0 / CPU4 |
|---|---:|---:|---:|
| Quente | 20,808 ms | 30,949 ms | 1,487 |
| Maior que a L3 local | 22,655 ms | 33,781 ms | 1,491 |

**ESTIMADO, cenário de sensibilidade.** Começando hipoteticamente em oito núcleos compactos distintos, uma equipa de quatro rápidos e quatro compactos teria taxa `(4r + 4) / 8` sob partição perfeita e taxas independentes. Este cenário retiraria 19,6–19,7% da duração do dot. A equipa real pode já estar distribuída pelos dois grupos. O cálculo concede taxas monothread constantes sob carga simultânea e ignora os restantes operadores, coordenação e alteração de residência na L3. O T2 histórico de 153 tokens precisava de retirar 8,360 s, 77,5% dos seus 10,784 s de prefill, mesmo concedendo decode a 6 tok/s na convenção de 47 saídas. Para a nova trajetória a decisão usa o seu próprio orçamento e a sua própria união de callbacks. [Relógios históricos](../../../nvme_conversation/postupdate/physical-result.md) · [Crivo do mesmo T2](../wait_bound.md)

A alternativa de espera passiva GOMP_SPINCOUNT=0 já obteve NO_GO, com quatro braços válidos e redução mediana do prefill incremental de −1,882%. A fixture CPU0 com uma wave ativa e sete estacionadas mediu 18,604–20,098 ms para o sufixo ON de uma tile. O controlo OFF só delimita esse sufixo entre zero e a duração do grafo e uma das quatro comparações falhou a banda do observador. A fusão das regiões estacionadas precedeu esta pergunta e não foi promovida. A diversidade de rotas, camada, width e partilha com a GPU impede multiplicar os números de uma tile para obter segundos no T2. [C225](../../../../C225-POST-C209-PASSIVE-WAIT-CLOSURE-20261001.md) · [Relógio CPU0](../../../cpu0_suffix/README.md) · [Fusão](../../../parked_fusion/timing/README.md)

## Decisão no próprio T2

O recibo do par PFJ1, SHA-256 `47476b0d8f0435c5e4c04f56a73edbb85f81e22ef9f9ba80a92c3b19b67d5b74`, arbitra dois contrafactuais diferentes no relógio do pedido. O T2 exigiu retirar 10,485 s até ao primeiro conteúdo final. Mesmo que todo o tempo exterior às callbacks caísse a zero, apenas se poupariam 5,997 s nesse modelo, restando **14,488 s**. A afinidade restrita ao FFN pode alcançar só uma parte desse complemento. Nas chamadas de prefill, as callbacks somam 7,028 s de união. O complemento é 3,718 s, perante 2,431 ou 2,597 s de orçamento total de prefill consoante a convenção de decode. Conservar toda a duração das callbacks já excede os dois orçamentos. [Definição dos relógios](../cliente.md) · [Contrafactual das callbacks](../wait_bound.md)

Mesmo concedendo todo o remap gratuitamente, o complemento de 3,718 s ainda teria de encolher 34,62% pela convenção de 47 saídas ou 30,14% pela de 46 avaliações. Aplicar os 19,7% de sensibilidade do dot a todo esse complemento ficaria aquém das duas condições. Isto encerra também essa combinação aditiva na geometria observada. A decisão de investir mudaria com uma interação mensurável que reduza o serviço e ultrapasse este cenário.

O crivo que concede agendamento ideal dentro do serviço tem outra hipótese. As 875 gerações exigidas pela sua própria wave até ao primeiro final deixam um piso de serviço de 6,232 s com quatro workers e durações de leitura observadas. Conservando os 5,997 s exteriores às callbacks, até o fator 0,8 no serviço deixa **10,982 s**. Os grupos de núcleos poderiam influenciar as leituras sob contenção; demonstrá-lo requer medir mudança do próprio serviço com as mesmas entradas, destinos e demandas. A incógnita de colocação dos threads é real, mas não sustenta investimento nesta afinidade como solução autónoma de M4. [Crivo do serviço obrigatório](../mandatory.md)

## Condição para ensaiar

Se o crivo no mesmo T2 ainda exigir apurar o cálculo fora da callback, medir primeiro a união de intervalos das MMID CPU nesse complemento, com PID e identidades de thread. Incluir os intervalos das waves sem falta. Um intervalo entre a última publicação e a chamada seguinte pode conter atenção, trabalho GPU, redução, entrega ao scheduler e espera. Se a união máxima atribuível ao cálculo visado for menor que a poupança necessária, fecha a via nesse regime. Uma discrepância nas frequências máximas dos núcleos não justifica outra sessão 120B.

Para distinguir escalonamento de variação no I/O, a menor experiência física proposta usa a tile CPU0 C266, os cinco experts já residentes e o ELF C269. Um percurso de preparação idêntico cria os quatro workers com a mesma máscara herdada, materializa e mede as cinco admissões e confirma o estado e os mesmos 40 slots. No percurso seguinte exigir zero leituras e zero SET de pesos, 92 160 F32 iguais ao gold e o mesmo grafo em todos os braços. O controlo R mantém a decisão do sistema operativo. A usa oito núcleos compactos distintos (4–11), B usa quatro rápidos e quatro compactos (0–7). Em A e B usar máscaras singleton atribuídas pelo threadpool GGML apenas ao cálculo. O testemunho fora do relógio comprova oito TIDs distintos, a máscara destes e dos quatro workers, os processadores observados e a topologia. Uma amostra pontual no controlo R deixa possíveis migrações entre observações. O contraste A/B testa o efeito da composição dos núcleos; só B/R testa um ganho face à política que já se usa. O relógio cobre o segundo grafo até à sincronização; a preparação, as barreiras e o custo de estabelecer afinidade conservam contabilidade própria. Este ensaio fica NOT_RUN. A alocação real do servidor e a necessidade de medir mais fases dependem do limite integrado.

```sh
lscpu -e=CPU,CORE,SOCKET,NODE,CACHE,MAXMHZ
cat /sys/devices/system/cpu/cpu{0,4}/cache/index3/{size,shared_cpu_list}
python3 -B research/qualification-retake/phase_fd/integrated/cpu_residual/screen.py \
  --closed-c281 "$C281_ORIGINAL_FECHADO" --new-output "$NEW"
cmp "$NEW" research/qualification-retake/phase_fd/integrated/cpu_residual/receipt.json
```
