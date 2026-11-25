# Vale a pena evitar a quantização de uma wave CPU inteiramente estacionada?

Pré-registo de 25 de novembro de 2026. A base integrada é 293f5b184da9439771cce361cd33fc4068d749f4 e a base imediata do estudo no PR 49 é be1f6a919823d8feec6b3ffa84d0b64438e412bf. No último segundo turno natural de R0 em NVMe, o prefill ocupou 10,784107 s e o primeiro conteúdo final chegou em 20,385070 s. A pergunta desta unidade é quanto trabalho se pode retirar ao grafo CPU de uma tile genuína mantendo bytes, valores e ordem de redução. [Pedido de produto](../nvme_conversation/postupdate/physical-result.md)

## Mecanismo e alternativa

No MMID do C269, o kernel converte as ativações para Q8_0 antes de tratar os IDs estacionados. A opção existente de R0 omite o produto peso × ativação em cada rank com ID físico −1 e escreve +0 no destino. Na variante, todos os workers examinam os IDs físicos da vista de prefill. Se todos forem −1, cada worker escreve +0 nas linhas de saída que lhe cabem e termina antes da conversão. Um único ID ativo mantém o caminho anterior para toda a vista. A intervenção tem âmbito MXFP4/F32 da CPU com mais de uma posição e com a política de parking de R0 ativa. Guarda o padding e as operações posteriores, incluindo biases, SwiGLU, máscara e adições. O retorno de um token, o router, a reserva de slots, o manager e o caminho CUDA conservam a implementação de R0.

A explicação concorrente é que a conversão evitável custa pouco face às leituras de pesos, operações posteriores, sincronização e variação da duração do grafo. O teste de todos os IDs também custa tempo quando há ranks ativos. Um primeiro rank estacionado seguido de um rank ativo partilha a ativação e deve produzir o dot do segundo rank. C57 já mostrou a falha da regra que olha só para o primeiro. [Contraprova C57](../../C57-BROADCAST-SHARED-ACTIVATION-20260928.md)

## Entrada, orçamento e exatidão

Usar a tile CPU0 de 32 posições, 32:64 da captura C266, router de 153 posições, cinco experts originais e pack privado autenticado. Uma wave ativa, sete estacionadas e três MMID por wave. R0 DENSE, 40 slots, quatro workers, oito threads GGML. Os três componentes preservam os bytes de peso e os SET. Por processo, a agenda requer cinco admissões, 66 109 440 B de leituras alinhadas e 66 096 000 B de payload lógico. Esta captura difere do pedido natural 5+148. [Entradas](../packed_real_layer/README.md) · [Estrutura do grafo](../cpu0_suffix/source.md)

Comparar o novo fornecedor com o original fixado e isolar a opção OFF/ON dentro do mesmo binário e fornecedor candidato. Desligar cb_eval e a marca da wave em todos os braços. Antes da família temporal, exigir contraprovas da condição de parking e igualdade integral com o gold independente da tile em três processos separados, original, OFF, ON. Cada nova execução volta a comparar os 368 640 B de saída, SHA-256 bf0391c5e7aad2aa22c730d56c07213fadcd0db1b7801d5dd58e1533f9aaba24. Uma divergência, não finito, troca de DSO, mudança de grafo, falha de recursos ou de cleanup termina a família e preserva o raw.

Congelar código e manifesto antes do build confirmatório. Registar compilador, comandos, objetos, DSO original e candidata, caminho resolvido e SHA de todos os fornecedores GGML. Congelar build e commit antes das execuções físicas. Cada processo começa com o manager vazio. A cache de páginas do SO pode estar quente. Limites herdados de packed_real_layer, C55 válida, C118 de 60 s, cgroup de 4 GiB, stop a 3,5 GiB, swap zero, até 720 s na família, 32 MiB de saída física, sem GPU compute. Onze processos da camada somam 727 203 840 B pedidos ao pack, além da autenticação dos inputs. Os testes de lógica ou de compilação ficam fora do cronómetro.

## Comparação temporal e saídas

Depois da igualdade, executar oito processos novos na ordem OFF ON, ON OFF, ON OFF, OFF ON. Medir CLOCK_MONOTONIC imediatamente antes de graph_compute do FFN e depois de synchronize. Inclui as waves ativas, falhas no manager, cópias e esperas do grafo. Router anterior, validação, encerramento e startup têm relógios distintos. Publicar os oito tempos, deltas OFF menos ON e rácios ON/OFF, mediana e amplitude dos deltas. Não escolher os melhores pares nem repetir a família por causa do sinal.

- **GO_TEST_NEXT** se os quatro deltas forem positivos e a mediana for pelo menos 1,000 ms por tile. É o mínimo de engenharia para investir em tiles com outras densidades de ranks e no gate numérico integrado. Não autoriza atribuir tempo ao pedido.
- **NO_GO_CPU0_TILE** se os quatro deltas forem menores ou iguais a zero, encerrando esta variante para a tile e regime ensaiados.
- **INCONCLUSIVE** nos outros casos. Identificar que parte da seleção de tiles ou da dispersão é necessária para uma decisão.
- Uma falha de integridade ou de medição produz **FAIL_PRESERVED**, com as fases e os custos que chegaram a ocorrer.

Os 737 grupos estacionados da call 148 em C135 permitem exprimir a escala que seria necessária. Um segundo de prefill exigiria 1,357 ms poupados em média por grupo estacionado no caminho crítico. O tempo medido numa única tile não identifica essa média. A call 5 usa uma wave direta. M3, M4, o outro caso e o desempenho de decode continuam sujeitos aos seus avaliadores próprios.
