# N2 — revisão externa e decisão pendente

Estado: `REVIEW_OF_PUBLISHED_DIAGNOSTIC / NOT_NEW_PHYSICAL_MEASUREMENT`.

PR consultada: #34, OPEN/draft, HEAD `f4d0a1a73e437493c77bcef21435631cf792f453`, base #33 em `ca532aaa765ad551dcb8be4424f0abe6778eec96`.

Measurement commit reportado: `05dc3e7fb8910674bc65c0abcd206a9cc5147fe0`; tree `9514bb9152de8caedc64f6e1b11c036cc0fbb2e0`.

## Fontes e âmbito desta revisão

Foram lidos no HEAD congelado:

- `research/VERTICAL-NUMERICAL-BLOCKER-N2-20260925.md`;
- `research/vertical-numerical-blocker-20260925/evidence-manifest-n2.json`;
- `research/vertical-numerical-blocker-20260925/diagnostic-233715/stage-analysis.json`;
- `research/vertical-numerical-blocker-20260925/diagnostic-233715/suffix-probe.json`;
- `src/tesy/vertical_numerical_diagnostic.py`.

A atribuição abaixo é sustentada por esses registos publicados, não por nova execução física. Nesta sessão não foram transferidos/recalculados os novos sidecars F32 por estágio do N2. A recomputação independente dos dois vectores finais históricos foi efectivamente repetida a partir do bundle C3 e coincide com a auditoria anterior; ver `c3-raw-20260925/`.

O source upstream pinado foi adicionalmente consultado: `ggml/src/ggml-cpu/ggml-cpu.c`, traits MXFP4, e `ggml/src/ggml-cuda/mmvq.cu`, quantização Q8_1 e dispatch por tipo. Isso confirma a existência dos caminhos aritméticos distintos. Não equivale a kernel trace que prove o dispatch realmente executado em cada operação da campanha.

## Conclusão admitida

**O FAIL continua válido. O N2 sustenta uma atribuição ao vector FFN do expert executado na GPU neste evento, mas não uma reparação nem uma prova de que a aritmética GPU está matematicamente errada.**

O diagnóstico deixou de depender apenas da correlação entre activar GPU e mudar logits:

- a rota publicada é `[4,0,31,17]`, com expert 0 na GPU;
- readbacks de pesos/biases/inputs foram registados como bytewise iguais;
- os três experts CPU foram bitwise stock nos oito estágios capturados;
- alterar só o output FFN em contexto stock reproduziu os logits do candidato;
- reinjectar o output stock preservou os logits stock.

Essa intervenção é muito mais forte do que a observação inicial. Se os controlos e hashes publicados forem aceites, o vector FFN é suficiente para explicar o erro final neste caso. Isto não prova a segurança geral da seam, todos os estados/KV ou todas as rotas.

## O que não deve ser confundido

### Primeira diferença observada não é necessariamente causa dominante do erro final

A replay segmentada encontrou a primeira diferença em `ffn_moe_gate`/`MUL_MAT_ID` do expert 0: max abs `2.384185791015625e-07`.

O input SwiGLU antes de down já difere: max abs `4.76837158203125e-07`. O output down difere em `0.002468585968017578`.

Assim, a diferença de down mistura duas alterações: backend e input. Não demonstra que o kernel down, com input idêntico, produza sozinho toda aquela diferença. Uma descontinuidade da quantização do input é uma hipótese plausível, não um diagnóstico demonstrado.

A segmentação também pode alterar fusion. O N2 documenta correctamente que o output final segmentado foi bitwise igual ao compacto normal, sem afirmar identidade de todos os intermediários do caminho não segmentado.

### Q8_0 e Q8_1 não são, por si só, uma prova de bug

O source CPU configura `ggml_vec_dot_mxfp4_q8_0`; o caminho CUDA MMVQ consultado usa `quantize_row_q8_1_cuda` e dispatch MXFP4. Os pesos de modelo permanecem MXFP4; o detalhe aqui inclui representação temporária dos inputs e organização aritmética.

Não atribuir a causa a um nome de formato, FMA ou ordem de acumulação sem um teste que a separe. A documentação NVIDIA explica que organização das operações e bibliotecas distintas podem produzir resultados diferentes conformes com o padrão, mas não certifica a correcção deste kernel nem altera o target Tesy.

Fonte geral, não prova específica do caso: https://docs.nvidia.com/cuda/floating-point/index.html (secções 2.2, 3 e 5.4).

### Não houve top-k diferente nos nodes observados

Segundo o probe, já existem diferenças de scores/weights do router da layer 3, mas não foi capturado top-k diferente. Portanto não atribuir este FAIL a uma troca de expert posterior que não foi observada. As diferenças podem propagar-se mesmo mantendo os IDs seleccionados.

### A redução foi separada, não corrigida como causa

A associação alternativa muda o FFN no máximo `4.76837158203125e-07`; aplicar a associação stock às contribuições mixed mantém o erro relativo FFN `4.125843157431181e-05`. O N2 não sustenta que mudar apenas a soma resolva o blocker.

## Decisão actual

- `HISTORICAL_FAIL = PRESERVED`.
- `VERTICAL_CORRECTNESS = BLOCKED`.
- `TESY_PERFORMANCE = NOT_RUN`.
- `LOCAL_TECHNICAL_REPAIR = NOT_DEMONSTRATED`.
- `BIT_LEVEL_KERNEL_CAUSE = NOT_ESTABLISHED`.
- `CPU_VS_GPU_STOCK_CONTRACT_CHARACTERIZATION = NOT_RUN`.

Não alterar o limite 0.005, redefinir o target como o resultado que passa, mover o expert problemático para CPU para fabricar PASS ou começar a escrever um kernel compatível com CPU sem avaliar a necessidade.

O target CPU é autoridade do contrato congelado; não é por isso automaticamente a solução matemática de maior precisão. Essas são perguntas diferentes.

## Implicação arquitectural

Residência de pesos e backend de cálculo são duas decisões distintas. Se a escolha CPU/GPU muda a aritmética, ligar essa escolha ao estado do cache pode mudar os logits e, noutras entradas, routing futuro, mesmo sem alterar explicitamente top-k.

Qualquer contrato futuro deve definir uma referência independente de cache/predictor, e preservar a diferença entre exact routing, numerical parity, igualdade greedy e preservação distribucional. Não aceitar uma definição circular na qual o target é simplesmente a própria política candidata.

## Próximo passo proposto, ainda não autorizado

Uma unidade limitada de caracterização, não nova arquitectura:

1. Matriz 2x2 da down projection com os dois inputs já capturados e os dois backends. Reutilizar operadores maduros; confirmar que os cantos diagonais reproduzem os outputs N2 antes de interpretar os cruzamentos. Isto separa o efeito de mudar input do efeito de mudar backend sem perseguir cada bit.
2. Comparação de logits completos de stock sem patch, CPU versus a colocação stock ngl12 já admissível, sobre o caso falhado e um caso independente previamente congelado. Serve para caracterizar o contrato entre execuções stock, não para absolver o candidato. Não é a mesma colocação de experts nem isola a layer 2; a atribuição causal continua a vir do N2 e da matriz controlada.

Sem timing, novos kernels, precision/quantization flags novas, mudança de residência do candidato ou promoção do FAIL. Se stock também exceder o contrato, isso desencadeia revisão prospectiva; não implica que o candidato passe. Se stock não exceder, o resultado também não prova uniformemente que toda execução GPU deva coincidir com CPU.

O mandato de execução desta proposta depende de aprovação do utilizador. A documentação desta proposta não é autorização implícita ao Codex.

## Governação

Esta revisão foi publicada numa branch de auditoria separada; não alterou #33/#34, CURRENT.json do Codex, protocolo de medição ou estados de acceptance. Não houve merge, force-push ou CI manual. A auditoria de N2 completa sobre os novos vectores continua distinta desta revisão documental/source.
