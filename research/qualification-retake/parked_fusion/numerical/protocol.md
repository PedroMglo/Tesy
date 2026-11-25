# Exatidão da fusão CPU sobre uma wave inteiramente estacionada

Pré-registo de 25 de novembro de 2026. O corte de seis nós é contíguo e passou o predicado de fusão do C269 nas oito waves da tile CPU0 antes e depois do scheduler. Esta unidade testa se a substituição mantém todas as saídas observáveis em entradas adversariais. O controlo original é o backend C269, com o mecanismo de parking R0 ativo. A ablação no mesmo fornecedor candidato permite somente o corte anterior por MMID. [Gate estrutural](../protocol.md) · [Ablação](../../parked_mmid/protocol.md)

## Prova e contraprovas

Exercitar GGML nativo CPU, MXFP4, ativações e resultado F32, ADD_ID com IDs lógicos, SwiGLU OAI e down. As três projeções usam os mesmos IDs físicos; um rank ativo basta para impedir a fusão. Exigir o predicado nativo para a região, os shapes/types/strides compatíveis, ausência de consumidores externos das temporárias e condições de execução que permitam omitir esses nós. Cada thread deve decidir da mesma forma. O candidato produz diretamente o tensor que o down original escreveria e mantém bias de down, máscara e adição ao acumulador nos nós originais. Os controlos incluem sinais de zero e valores finitos muito pequenos. Não alterar a acumulação de uma wave posterior.

Antes de quaisquer timings, comparar resultados completos byte a byte em processos novos. Quatro modos, sujeitos aos mesmos dados e ao mesmo orçamento: biblioteca original, candidata com todas as alterações desligadas, candidata só com o corte MMID, candidata com MMID e fusão. O controlo negativo verifica casos mistos, último rank ativo, uma única posição de decode, reutilização do grafo quando os IDs mudam, e um intermediário exposto ou um nó que quebra o trecho contíguo. Incluir diferentes larguras de prefill e equipas de uma e várias threads. Conservar a identidade de cada caso, braços e saídas para verificar o denominador. Exigir um testemunho positivo do ramo de fusão nos casos elegíveis e zero nos casos protegidos. O contador de diagnóstico fica fora de qualquer relógio de produto.

Orçamento: uma família de exatidão sem modelo por identidade, CPU apenas, zero downloads, zero pesos reais, zero GPU e zero forwards do target. O cgroup tem cap de 4 GiB, stop a 3,5 GiB e swap zero. O compilador, DSO e intervenções são privados da unidade; autenticar os três inputs de fonte e o original C269 e selar o build/saídas. Falha de build, integridade, limite ou execução encerra a identidade e conserva o recibo. Uma correção técnica usa outra identidade.

- **GO_REAL_TILE** exige todos os modos e casos previstos, saídas finitas idênticas em todos os bits, testemunhos de fusão exatamente conforme o esperado e todos os limites verificados. Abre a qualificação numa tile real.
- **NO_GO_EXACTNESS** se a substituição produzir um bit divergente ou tomar o ramo em circunstância proibida num confronto identificado. Conservar a primeira contraprova, o braço e a posição.
- **INCONCLUSIVE** se não for possível identificar a execução do corte ou a sua saída ou separar uma falha do harness.

O resultado diz respeito às entradas, tipos, backend e opções exercitados. A qualificação de um mecanismo no produto requer referência e ablação na configuração de 120B, estabilidade do primeiro decode e os tempos definidos pelo cliente. [Referência natural já medida](../../nvme_conversation/postupdate/physical-result.md)
