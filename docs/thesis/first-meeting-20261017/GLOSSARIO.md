# Glossário Tesy — termos para a reunião e futura tese

Definições **curtas mas precisas**, em português de Portugal. Nomes técnicos mantidos no original. Os termos com **Tesy** são relevantes para os mecanismos experimentais concretos; não confundas nomes de sistemas externos com partes do nosso runtime.

## 1. Modelos e inferência

| Termo | Significado |
|---|---|
| **LLM** (*Large Language Model*) | Modelo de linguagem treinado com muitos parâmetros para prever e gerar tokens. |
| **120B** | Aproximadamente 120 mil milhões de parâmetros totais; num MoE, não são todos ativados por token. |
| **Parâmetro / weight** | Valor aprendido que participa nas operações do modelo. |
| **Modelo dense** | Usa tipicamente o mesmo conjunto principal de parâmetros por token nas suas camadas. |
| **MoE** (*Mixture-of-Experts*) | Arquitetura que combina vários módulos FFN (*experts*) e escolhe apenas alguns em cada posição. |
| **Expert** | Sub-rede, tipicamente FFN, selecionada pelo router para processar uma representação. |
| **FFN** (*Feed-Forward Network*) | Parte da camada Transformer que transforma cada representação por projeções e ativações. |
| **Router / gate** | Computação que atribui pontuações aos experts e determina os escolhidos. |
| **Routing sparsity** | Seleção de uma fração dos experts disponíveis por token, reduzindo cálculo ativo. |
| **top-k** | Número de experts escolhidos pelo router para cada token/camada; no Tesy o valor autoritativo não é reduzido para ganhar performance. |
| **Transformer** | Arquitetura com attention e operações de transformação, usada nos LLMs modernos. |
| **Attention** | Mecanismo que combina informação de diferentes posições do contexto. |
| **Q / K / V** | *Queries*, *Keys* e *Values*: tensores usados para calcular atenção. Não são os experts. |
| **KV cache** | Armazenamento de Keys e Values de posições já processadas para evitar recalcular attention no decode. |
| **Token** | Unidade de texto convertida em ID por um tokenizer; não coincide necessariamente com palavra. |
| **Tokenizer / template** | Regras para converter texto em IDs e estruturar mensagens de chat. |
| **Contexto / context window** | Número máximo de posições/tokens que a sessão pode usar na configuração avaliada. |
| **Prompt** | Entrada fornecida ao modelo, já incluindo histórico e instruções quando aplicável. |
| **Prefill** | Processamento do prompt para criar o estado da sessão antes da geração incremental. |
| **Decode** | Geração incremental dos tokens seguintes a partir do contexto existente. |
| **Sampling / greedy** | Métodos de seleção do token seguinte; *greedy* escolhe o maior score/probabilidade no perfil definido. |
| **EOG / EOS** | Marcadores especiais de fim de geração/fim de sequência; podem entrar na contagem do backend. |

## 2. Formatos, hardware e memória

| Termo | Significado |
|---|---|
| **GGUF** | Formato de ficheiro usado pelo ecossistema llama.cpp para metadados e tensores do modelo. |
| **MXFP4** | Formato de pesos em precisão muito baixa usado no GPT-OSS; é o formato original deste target, não uma requantização feita pelo Tesy. |
| **BF16 / FP16 / F32** | Formatos de ponto flutuante com propriedades diferentes de precisão, gama e custo de memória. |
| **Quantização** | Representar pesos/ativações com menos bits; poupa memória mas pode alterar custo dos kernels e aritmética. |
| **Lossless** | Transformação reversível em que os valores/bytes originais são recuperados exatamente. |
| **Tensor** | Estrutura de dados multidimensional usada em cálculos do modelo. |
| **CPU** | Processador geral do sistema; pode executar operações e gerir transferências. |
| **GPU** | Processador paralelo usado para cálculos matriciais; tem VRAM limitada neste portátil. |
| **CUDA** | Plataforma e interfaces da NVIDIA para executar trabalho na GPU e mover dados. |
| **Kernel** | Operação computacional compilada/executada num backend CPU/GPU. |
| **VRAM** | Memória dedicada à GPU; a RTX 4060 Laptop de referência tem cerca de 8 GiB. |
| **RAM** | Memória principal do host; não tem o mesmo acesso/latência que a VRAM. |
| **NVMe / SSD** | Armazenamento persistente; costuma ter maior latência do que RAM/VRAM. |
| **PCIe** | Interligação utilizada, entre outros fins, para mover dados entre host e GPU discreta. |
| **Multi-tier storage** | Organização dos dados por níveis (ex.: NVMe, RAM, VRAM), cada um com custo/capacidade próprios. |
| **Bandwidth** | Quantidade de dados movimentados por unidade de tempo; depende do tier e operação. |
| **Latency** | Tempo decorrido até um evento ou resultado; não é a mesma coisa que bandwidth. |
| **Out-of-core** | Execução em que parte substancial dos pesos/dados está fora da memória rápida e é carregada sob necessidade. |

## 3. Técnicas investigadas no Tesy

| Termo | Significado |
|---|---|
| **Offloading** | Colocar ou executar parte dos dados/trabalho fora da GPU para cumprir o budget. |
| **Expert residency** | Conjunto de experts cujos pesos estão presentes num tier/cache num dado momento. |
| **Streaming de experts** | Carregamento seletivo de pesos à medida que os experts são exigidos. |
| **Slot** | Espaço da cache reservado para receber os pesos de um expert; mais slots implicam maior capacidade/memória. |
| **Cache hit / miss** | Hit: expert disponível na cache; miss: requer carregar/disponibilizar pesos. |
| **Eviction** | Substituir um expert residente por outro quando é necessário libertar um slot. |
| **LRU / Belady** | LRU remove o menos recentemente usado; Belady é política ótima com conhecimento futuro, útil como limite offline, não como executor causal. |
| **Prefetch** | Tentar antecipar dados antes de serem formalmente exigidos; no Tesy não decide o routing nem confirma tokens. |
| **Staging** | Área transitória para preparar pesos antes do seu destino final. |
| **O_DIRECT / pread** | Interface de I/O Linux; pread lê posições do ficheiro; O_DIRECT pode contornar page cache. Bytes pedidos não são automaticamente tráfego físico medido. |
| **Overlap** | Sobreposição temporal de compute e transferências que, se existir janela útil, pode esconder parte do custo. |
| **Wave** | Grupo de experts usado numa passagem quando não há slots para a união completa do microbatch. |
| **Wave skip (Tesy C75/C104)** | Evitar FFN/multiplicações para pares de expert/token que não contribuem na wave corrente. |
| **Tile / microbatch (ubatch)** | Subconjunto de posições calculado em conjunto; tile também descreve o bloco em certas reorganizações. |
| **Tile-major / expert-major** | Ordenar execução por tiles primeiro ou por experts primeiro, para potenciar reutilização de cada carregamento. |
| **Gather / scatter / reduction** | Reunir entradas, distribuir outputs e combinar contribuições, mantendo identidade/ordem relevantes. |
| **Lossless layout (Tesy C293)** | Reorganizar componentes originais de pesos por expert sem substituir valores ou routing. |
| **Speculative decoding** | Um modelo auxiliar propõe tokens; o target valida antes de confirmar as saídas. |
| **EAGLE-3** | Família de *draft heads* que propõe tokens com features do target; a integração testada em C258 foi mais lenta. |

## 4. Métricas, verificação e investigação

| Termo | Significado |
|---|---|
| **tok/s / throughput** | Tokens de output por segundo; tem de declarar contagem (confirmados, nativos, EOS) e regime. |
| **TTFT** (*Time to First Token*) | Latência até ao primeiro token; pode diferir do primeiro conteúdo final visível ao utilizador. |
| **First-final** | Tempo até começar conteúdo de resposta final útil, após eventual reasoning do modelo. |
| **TPOT** (*Time Per Output Token*) | Tempo médio ou distribuído entre tokens de output na fase incremental, com definição explícita. |
| **Warm / cold** | Warm pode reutilizar estado/contexto já preparado; cold começa sem esse contexto previamente residente. É preciso declarar o que foi aquecido. |
| **End-to-end** | Tempo completo da operação útil, incluindo overhead que microbenchmarks isolados podem ignorar. |
| **Microbenchmark / operador** | Teste isolado de uma função/etapa; o ganho pode não se transferir à inferência completa. |
| **Baseline stock** | Backend original sem as alterações específicas do Tesy, congelado para comparação justa. |
| **R0 / R1 / R2** | Nomes de perfis do Tesy para distinguir percurso autoregressivo original e caminhos experimentais com aritmética/shape diferentes. |
| **Bitwise equality** | Os bytes de resultados comparados são idênticos dentro do contrato/shape verificado. |
| **Numerical parity** | Resultados aproximados dentro de tolerância numérica pré-definida; não significa identidade bitwise. |
| **Greedy token equality** | Os IDs escolhidos por greedy coincidem no conjunto medido; não garante igualdade de logits ou sampling geral. |
| **Sampling distribution preservation** | A distribuição de outputs do target é conservada pela regra de amostragem; exige prova específica. |
| **Paired A/B / ABBA** | Comparações de dois perfis em pares, alternando a ordem para reduzir enviesamentos operacionais. |
| **Holdout** | Trabalho reservado antes das decisões e não usado para escolher parâmetros/candidatos. |
| **Gate** | Critério fixado para decidir investimento ou promoção de uma implementação; não define por si só validade científica geral. |
| **M3 / M4** | Marcos internos do Tesy; M3 continua parcial e M4 não está cumprido. |
| **MEDIDO / INFERIDO / ESTIMADO / NOT_RUN** | Etiquetas de evidência: medição efetiva, conclusão derivada, modelo de previsão, ou ensaio não executado. |
| **Prior art** | Trabalhos científicos/técnicos anteriores que limitam uma possível claim de novidade. |
| **Roofline / capacity bound** | Estimativas de teto físico por compute, tráfego e capacidade; não substituem cronometrações integradas. |

## 5. Sistemas e artigos citados

| Nome | O que é e porque aparece |
|---|---|
| **Shazeer et al. (2017)** | Trabalho seminal sobre routing sparse e conditional computation em MoE. |
| **Switch Transformers** | Trabalho de Fedus, Zoph & Shazeer sobre escalabilidade de MoE e routing simplificado. |
| **HOBBIT** | Sistema de *expert offloading* com mixed precision para inferência MoE em edge (Tang et al., 2024). |
| **fMoE (2025)** | *Fine-Grained Expert Offloading for Large Mixture-of-Experts Serving*, de Yu et al.; é offloading/caching/prefetch em serving. |
| **FastMoE** | Biblioteca/sistema diferente, direcionado a treino distribuído de MoE. **Não é sinónimo de fMoE (2025).** |
| **llama.cpp** | Backend de inferência que o Tesy usa como base e baseline a congelar; não é uma contribuição inventada pelo Tesy. |
| **Ollama** | Ferramenta de execução/serving local; só é baseline científico se versões, configuração e recursos forem comparáveis. |

## Como usar
Antes da reunião, aprende bem: **MoE, router/top-k, expert residency, wave-skip, layout lossless, prefill/decode, first-final, baseline, bitwise e fMoE**. Na conversa, define cada termo uma vez e só quando for necessário; o glossário é material de apoio e base para expandir a secção de terminologia da tese.
