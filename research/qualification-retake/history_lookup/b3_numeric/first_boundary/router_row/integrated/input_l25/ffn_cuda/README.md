# Na camada CUDA 25, bastou calcular a projeção down por posição

**GO para integrar apenas down e o seu bias.** Na RTX 4060 do portátil, a FFN isolada reproduziu bit a bit as duas saídas capturadas no GPT-OSS-120B completo. Com as mesmas entradas, os mesmos dez experts MXFP4 e os mesmos pesos do router, calcular down por posição recuperou as 8 640 palavras F32 da execução serial. Gate, up, SwiGLU, ponderação e soma dos quatro ranks continuaram em bloco. A divisão do primeiro grupo sozinha conservou todas as 171 diferenças. O resultado vale para estas três posições em L25. O melhor turno nominal de produto continua em 18,313 s e 5,361 tok/s. [Pré-registo](protocol.md) · [Saídas por posição](result.json)

| Grafo | F32 diferentes de AR em 189 / 190 / 191 | F32 diferentes do bloco do modelo nas mesmas posições |
|---|---:|---:|
| A, três FFN seriais | 0 / 0 / 0 | 33 / 29 / 109 |
| B, toda a FFN em bloco | 33 / 29 / 109 | 0 / 0 / 0 |
| U, só gate/up/SwiGLU por posição | 33 / 29 / 109 | 0 / 0 / 0 |
| D, só down com bias por posição | 0 / 0 / 0 | 33 / 29 / 109 |
| S, ambos os grupos por posição | 0 / 0 / 0 | 33 / 29 / 109 |
| F, toda a FFN por posição num grafo | 0 / 0 / 0 | 33 / 29 / 109 |
| B-alt e F-alt, dez slots diferentes | Idênticos a B e F respetivamente | Idênticos a B e F respetivamente |
| B-alt com um bias down alterado | 34 / 29 / 109 | 1 / 0 / 0 |

Cada coluna compara 2 880 F32 por posição. As diferenças máximas absolutas de B contra AR foram 0,00048828125, 0,0001220703125 e 0,000244140625. A mutação alterou exclusivamente a coordenada zero da posição 189, a única que selecionou o expert 107. Os quartetos ordenados foram 107/63/76/66, 66/39/6/86 e 6/105/77/95. Os dois mapas de slots são testemunhas da reconstrução. Os IDs físicos da execução histórica continuam desconhecidos. O teste localiza a intervenção suficiente no conjunto down+bias. A identidade do kernel CUDA que causou o desvio permanece por observar. [Extração dos operandos](operands.py) · [Grafo e contraprova](fixture.cpp)

A preparação releu 132 192 000 bytes de matrizes e 345 600 bytes de biases no GGUF original, em 60 intervalos autenticados. O processo CUDA executou onze grafos em nove braços. Zero forwards do 120B, zero pedidos de geração. O scope de execução demorou 1,728 s, com pico de cgroup de 226 312 192 B e swap zero. A ocupação total da GPU passou de 2 MiB para 612 e 622 MiB nas duas amostras e regressou a 2 MiB. Essa janela, que inclui cópias, controlos e mutação, não mede o custo do decode nem a energia por token. A identidade da execução foi `9ad04501`. O revisor inicial colidiu o nome de uma variável no parser do inventário. Corrigido o revisor, originais e arquivo deram o mesmo SHA-256 `52a205f6a289a29eb9c7af4b2736c927a572c84e544ac5ba8e8a8f75aafc0ca7`. [Revisor sem GPU nem GGUF](review.py) · [89 ficheiros privados](../../../../../../../private_archive/part-168.json)

Em 26 de novembro, o antecedente negativo mais próximo encontrado foi a medição dos autores do issue vLLM #57016. Na versão 0.27.1 observaram sensibilidade da seleção de kernels MoE à população do batch em bf16 em Hopper, e à quantização online em fp8 em testes com RTX 4090 e H100. Os seus braços usam pedidos concorrentes ou prefill frio versus prefixo já em cache. Aqui medimos uma única sequência, três posições, Ada, MXFP4 com índices remapeados e bytes de dois forwards independentes. A documentação v0.34.0 restringe a cobertura verificada a combinações de backends e modelos. O resultado de L25 permite escolher onde intervir neste pin. [Observação e matriz por modelo](https://github.com/vllm-project/vllm/issues/57016) · [Cobertura documentada](https://docs.vllm.ai/en/v0.34.0/features/batch_invariance/)

LLM-42 verificou o valor de restaurar o KV na verificação de blocos. A avaliação usou Llama-3.1-8B-Instruct, SGLang 0.5.3rc0, quatro H100 PCIe de 80 GB e 1,65 TB de DRAM no host. O agrupamento de janelas de vários pedidos reduz o custo por token nessa carga. A comparação Tesy seguinte deve medir novamente o KV e os logits completos com apenas a conversa local, antes de atribuir tempo poupado. M3 PARTIAL, M4 NOT_MET. [Método e avaliação de LLM-42](https://arxiv.org/html/2601.17768v2)
