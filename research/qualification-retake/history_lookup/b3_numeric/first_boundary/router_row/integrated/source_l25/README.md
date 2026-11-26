# A entrada que separa a projeção do router da atenção na camada 25

**O controlo AR já contém o operando exato.** C270 conservou `attn_post_norm-25` e os 128 logits *antes* do bias nas posições 189 e 190. As mesmas quatro linhas do C127 ON e OFF reproduzem os bytes do C270. Falta o operando correspondente no B3 integrado. Só por esse motivo não é possível atribuir ao router os 128/128 padrões diferentes observados em cada uma destas posições. As capturas B3 das partes 32, 102 e 108 também não conservam neste ponto Q, K, V, o residual de saída da camada 24 ou a saída da atenção de 25. Os KV serializados são estados da cache após a conversão e a escrita, e não fornecem Q nem o operando F32 de entrada do router. [Recibo com os SHA completos](receipt.json) · [Contraste integrado](../README.md)

| Posição | AR · entrada de 2880 F32 | AR · produto de 128 F32 | B3 ON |
|---|---|---|---|
| 189 | `decode0_25_attn_post_norm_2422.bin` · `974d5427…` | `decode0_25_ffn_moe_logits_2423.bin` · `1e81205c…` | Produto disponível, entrada ausente |
| 190 | `decode1_25_attn_post_norm_2674.bin` · `b49a8146…` | `decode1_25_ffn_moe_logits_2675.bin` · `18a87fa5…` | Produto disponível, entrada ausente |
| 191 | Sem referência AR nesta captura | Sem referência AR nesta captura | Produto disponível, entrada ausente |

O índice C270 regista a fase, a posição absoluta, `state_tokens=1` e a geometria. As linhas estão na parte 23, em `tesy-c270-driver-20261125-r01/raw/tesy-c270-driver-20261125-r01.capture/`. O índice também contém as posições 196 e 220, relativas a outros passos. O manifesto da parte 108 autentica os produtos B3 de 189–191 em `ON/raw/*.capture/boundary/`. O verificador releu os quatro controlos, os produtos OFF/ON, a informação de colocação e os manifestos. A cobertura restringe-se aos índices e campanhas identificados. [Verificador](check.py) · [Protocolo e pins](protocol.md)

### O caminho no target C269

Os nomes e linhas abaixo referem-se ao backend `d0ebfbcc6c8f456bc1083027c1b08075a32824d8`. O inventário GGUF identifica os quatro pesos das projeções da atenção de 25 como Q8_0 e o peso do router como F32 [2880,128], no offset 45 558 240 288 e com 1 474 560 B. O log do mesmo ON identifica a RTX 4060 Laptop (SM 8.9), camada 24 CPU/SWA e camada 25 CUDA0/atenção completa, KV de 25 no dispositivo e Flash Attention ativada. O carregador deteta as três matrizes Q/K/V separadas. A execução exata de cada kernel dentro do split não foi instrumentada. [Inventário do recorte](receipt.json) · [Fontes autenticadas](protocol.md)

| Ordem | Tensor e operação | Fonte no pin |
|---|---|---|
| 1 | O FFN de 24 soma-se ao seu residual para produzir `l_out-24`. A camada 25 reutiliza esse tensor e executa RMS_NORM e multiplicação pelo peso da norma. | `src/models/openai-moe.cpp:147–153,77–89` e `src/llama-graph.cpp:1450–1473` |
| 2 | Três MUL_MAT+bias sobre a entrada normalizada e reshape. RoPE em Q e K, V sem RoPE. Q tem 64 cabeças, K/V têm 8, dimensão 64. | `src/llama-graph.cpp:1519–1556`, `src/models/openai-moe.cpp:93–115` |
| 3 | Seleção da cache base e máscara causal, escrita de K/V, atenção com sinks e escala 1/√64, projeção de saída Q8_0 e bias F32. | `src/llama-graph.cpp:2968–3039,2495–2517` |
| 4 | `ffn_inp-25 = attn_out-25 + l_out-24`. RMS_NORM e multiplicação por `post_attention_norm.weight` dão `attn_post_norm-25`. O filtro de saídas só ocorre na camada 35. | `src/models/openai-moe.cpp:117–136` |
| 5 | O router calcula a projeção pre-bias. Em B3 ON são três vistas do mesmo operando, três produtos de largura 1 com o mesmo peso e dois CONCAT no eixo de posições. Seguem-se bias, top-4 e softmax dos quatro pesos. Os experts e a redução estão a jusante deste produto. | `src/llama-graph.cpp:1824–1857,1910–1936` e [intervenção C269](../source.py) |

O carregador escolhe o dispositivo por camada em `src/llama-model.cpp:1367–1388`. A norma interna chamada `norm` tem preferência explícita pelo dispositivo da camada para microbatches com menos de 32 tokens, se o backend suportar a operação (`src/llama-context.cpp:2516–2527`). O scheduler também considera os buffers de pesos e o suporte do backend (`ggml/src/ggml-backend.cpp:916–945`). Igualdade dos routers 14–24 não certifica `l_out-24`. Podem existir diferenças anteriores aos primeiros 128 valores observados em 25.

**Duas hipóteses concretas dependem da geometria.** Para peso F32 contíguo e alinhado em Ada, o seletor MMVF admite até três colunas. Os casos de largura 1 e 3 têm instanciações próprias. Assim, a distinção CPU entre dot e SGEMM medida na camada 0 não identifica o caminho CUDA. Além disso, no B3 ON o router já usa os produtos de uma coluna; as projeções Q8_0 de Q/K/V e da saída e a atenção continuam a receber três posições. O backend dispõe de MMVQ com parametrizações de largura 1 e 3. O seletor de Flash Attention em Ada também distingue uma query de três, dependendo entre outros de tipos, forma real de K, máscaras e alinhamento. Os 8192 lugares de capacidade não identificam a extensão da vista de K entregue à operação. Os ramos e fusões possíveis são hipóteses de localização. Fontes no pin: `ggml/src/ggml-cuda/ggml-cuda.cu:2571–2659,4248–4295`, `mmvf.cu:541–562,786–812`, `mmvq.cu:890–927`, `fattn.cu:448–478` (os três últimos em `ggml/src/ggml-cuda/`).

### O menor contraste que muda a decisão

No mesmo B3 ON e no mesmo estado de 189 tokens, guardar as três colunas de `attn_post_norm-25` antes dos produtos. São 34 560 B adicionais; os 23 040 B das duas primeiras colunas têm controlo AR externo. Validar tipo, shape, strides, offsets das views, peso e ordem do CONCAT; conservar o produto pré-bias de 108, os restantes valores já observados, os logits finais e o estado. O callback de leitura sincroniza e separa a execução do grafo (`ggml/src/ggml-backend.cpp:1678–1711`), pelo que um observador que mude testemunhos torna a comparação inconclusiva.

- Se o operando for igual e o produto continuar diferente, a fronteira observável fica entre a aplicação dos mesmos pesos e a publicação do CONCAT. Capturar as saídas de cada MUL_MAT e permutar as duas primeiras colunas apenas num controlo offline para verificar a associação posicional. As duas entradas e os dois produtos AR têm hashes distintos.
- Se o operando diferir, a divergência já chegou ao router. Para distinguir propagação de um efeito adicional da projeção, executar a projeção CUDA separadamente alimentada com a mesma linha AR nos dois layouts; testar também a linha B3 efetivamente adquirida. Uma entrada diferente não prova que o produto apenas propaga a diferença. Para interrogar a origem a montante, conservar `l_out-24`, norma, Q/K/V, atenção e residual de 25. Uma comparação AR desses estágios adicionais necessita de referências próprias, salvo o que o novo teste puder deduzir do mesmo operando.
- A posição 191 pode servir de testemunho B3. Qualificação bitwise face a AR nessa posição exige uma referência adicional.

Reprodução do censo sem ler o modelo nem iniciar o backend:

```sh
python3 -IB check.py --archive /mnt/sdisk-ssd-ext/Tesy/outputs/qualification-20261124-nvme-01 \
  --c7 /mnt/sdisk-ssd-ext/Tesy/repo/c7-native-placement-screen-20260927-1117utc
```
