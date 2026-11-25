# O custo físico do prefill combinado com o decode do mesmo turno

**MEDIDO no portátil.** Mantendo os mesmos quatro workers e os pesos no mesmo NVMe, o pack reduziu a soma das barreiras das duas chamadas em **1,473 e 1,747 s**, ou **20,99% e 24,72%** nos pares RP e PR. A chamada de 5 pede 449 452 800 B de payload, a de 148 pede 13 536 460 800 B. O tratamento abre a FIFO completa de cada chamada e espera antes de passar à próxima. A autorização antecipada de todas as leituras dentro da chamada dispensa o router e as dependências internas. [Plano por tile e camada](../prepare/README.md) · [Protocolo físico e integridade](../service/protocol.md)

| Ordem | Layout | Chamada 5 (s) | Chamada 148 (s) | Soma do serviço (s) | GB/s úteis | Tempo na chamada 148 com quatro preads em voo |
|---|---|---:|---:|---:|---:|---:|
| RP | R | 0,225 | 6,794 | 7,019 | 1,993 | 99,59% |
| RP | P | 0,208 | 5,338 | 5,545 | 2,522 | 99,59% |
| PR | P | 0,174 | 5,147 | 5,321 | 2,628 | 99,46% |
| PR | R | 0,234 | 6,834 | 7,068 | 1,979 | 99,65% |

A coluna de concorrência mede a sobreposição das chamadas do processo a pread. O dispositivo tem as suas próprias filas. No ensaio físico, cada layout ficou aberto por um único FD O_DIRECT autenticado em cada processo. Primeiro foram temporizados os dois layouts. Na travessia seguinte o programa confirmou todos os hashes das três matrizes de cada expert nos mesmos FDs e orçamentou separadamente essa leitura e cálculo. O revisor voltou a verificar a sequência, a identidade dos 1 058 jobs, a concorrência e os 3 174 digests de cada segunda travessia. [Quatro braços e recursos](../service/README.md)

## Margem condicional até aos 10 segundos

A cada preço físico do prefill do pack acrescentámos cada um dos dois preços já publicados de decode do pack (7,084608 / 7,116859 s). Estes preços de decode conservam o exterior R0, os SET com homólogo e as 47 saídas. A última coluna converte o tempo disponível para ler em número de experts inteiros de 13 219 200 B à taxa média de cada travessia, com a mesma proporção de trabalho das duas chamadas. É uma sensibilidade a banda fixa. Cada nova população de leituras e os seus custos têm de ser medidos na própria agenda. [Protocolo](protocol.md) · [Recibo reproduzido](receipt.json)

| Ordem prefill | Ordem decode | Margem serial (s) | Margem com pipeline ideal (s) | Margem com todas as lacunas grátis (s) | Máximo de experts ao mesmo débito (serial / pipeline / sem lacunas) |
|---|---|---:|---:|---:|---:|
| RP | RP | -3,563 | -2,771 | -2,412 | 378 / 529 / 597 |
| RP | PR | -3,595 | -2,803 | -2,444 | 372 / 523 / 591 |
| PR | RP | -3,338 | -2,547 | -2,187 | 394 / 551 / 623 |
| PR | PR | -3,371 | -2,579 | -2,220 | 387 / 545 / 616 |

**NO_GO para a suficiência da combinação a estes preços.** Mesmo concedendo custo zero a todas as lacunas, faltam 2,187–2,444 s nas quatro combinações. O ganho marginal medido do pack conserva-se. Para decidir a intervenção seguinte, o mínimo offline no próprio T2 é 787 leituras com os conjuntos do carry fixos nos retornos de 5 e 148, ou 734 com ambos livres. Estas quantidades admitem conhecimento futuro e cópias gratuitas. O preço dos 797 jobs do decode só se volta a aplicar se a política reproduzir o estado e a agenda dessa fase. Aumentar a sobreposição sem também alterar volume, serviço de disco ou preço do decode tem a margem publicada na tabela. [Limites offline deste T2](../../oracle/README.md) · [Troca causal de pesos entre RAM e primário](../../../exclusive_bank/README.md)

M3 PARTIAL e M4 NOT_MET. O último par natural de diagnóstico mediu 20,754 e 20,793 s para o primeiro conteúdo final e 4,663 e 4,645 tok/s. Este ensaio físico leu pesos MXFP4 autênticos em CPU, sem forward e sem novo pedido ao cliente. O cenário de latência conjunta assume um caminho de prefill que paga o preço de serviço medido. Uma mudança de agenda que o esconda sob outros trabalhos ou mude a distribuição dos pedidos exige reconstruir o caminho crítico.

Mesmo juntando os dois preços mais favoráveis e apagando todas as lacunas, caberiam cerca de **623 leituras** ao débito médio observado. O melhor piso das variantes de seleção com o banco fixo e ambos os conjuntos de saída livres é **734**. Isso aponta a uma diferença de pelo menos 111 leituras inteiras equivalentes se os outros preços se mantiverem. O piso usa conhecimento futuro e a conversão de bytes usa a taxa de outra população. A condição para reabrir é medir uma forma de transportar menos bytes por expert, aumentar as presenças úteis à entrada da fase ou reduzir o preço do decode no mesmo pedido. O operador CPU_Mapped fornece uma implementação para ensaiar a retenção de páginas com o último consumidor. Precisa de provar a capacidade adicional efetivamente disponível dentro do mesmo cap e o número de leituras distintas poupadas. [Implementação e resultados de paridade](../../../cpu_alias/mixed/README.md)

## Reprodução com os arquivos locais

A parte 69 guarda os planos e o banco exclusivo. A parte 70 guarda o oráculo, a C55 recusada e o recibo da transferência de nove worktrees de medições terminadas do tmpfs para a área ignorada de build do Tesy no SSD externo. A transferência preservou os ficheiros, os commits e os caminhos de acesso. A disponibilidade observada passou de 23 036 012 a 24 112 152 KiB. O serviço continuou a ler ambos os layouts do NVMe interno. A parte 71 guarda a C55 admitida, os dois processos e duas revisões em 22 ficheiros, 3 378 022 B, sob o manifesto `6e6b4ca1bd6f41477f8928c7cab6b72432cf3c47d923ede8be20e71231f05646`. Os quatro braços pediram 55 974 846 464 B cronometrados e outros tantos na autenticação posterior. Os três processos CPU de reanálise demoraram 0,07/0,08/0,07 s, com até 31 736 KiB de RSS. O terceiro abriu as cópias de arquivo das partes 69 e 71, reproduzindo o SHA-256 `78a53e6d93fed1ad9a9236d74b60b234546d32041f5e572998240b243b82fb7e`. O pré-registo conjunto é `6e08e19b`, a aritmética `e3c09838` e a revisão de gerações e digests `912d1756`.


```sh
u=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/prefill_frontier/transport/joint
timeout 120 prlimit --as=536870912 --cpu=120 python3 -IB "$u/review.py" \
  --plan "$PART69/tesy-prefill-transport-plan-20261125-r01/plan.json" \
  --plan-sha256 f54b60d5389d4ff503c978e9eed6065e87e0c08a3a245de17d1f59f58e3a152f \
  --first "$PART71/tesy-prefill-bandwidth-20261125-r01" --first-sha256 d966d8ac66a437c87e87d20cec270a490745e59f3ec9f7893b240943cc29aa18 \
  --second "$PART71/tesy-prefill-bandwidth-20261125-r02" --second-sha256 6a3c34118447a38d6047725b98ace54591b9d9e1be96789d0dd4d794a9398b92 \
  --new-output-dir "$NEW"
```
