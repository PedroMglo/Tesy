# O controlo do router falhou no quarto expert de uma linha CUDA de prefill

**INCONCLUSIVE para antecipar o top-4 em uma ou duas camadas.** No próprio operando do router, a projeção F32 local reproduziu a escolha ordenada de **3 399 das 3 400 linhas** do C270. Na posição 6 da primeira tile, camada 25, promoveu o quinto expert ao quarto lugar. A soma dos logits pré-bias arquivados com os biases originais recuperou os quatro IDs ordenados em **3 400/3 400**. O pré-registo exige calibração completa do projetor. As previsões futuras e os seus contrastes de recência ficaram sem pontuação. [Protocolo](protocol.md) · [Recibo das duas execuções](receipt.json) · [Localização independente](localization.json)

| Controlo na própria camada | Linhas | Quarteto ordenado igual | Palavras de logits com bits diferentes / total | Máximo erro absoluto pré-bias |
|---|---:|---:|---:|---:|
| Prefill, destino CPU | 2 325 | 2 325 | 265 862 / 297 600 | 0,000002862 |
| Prefill, destino CUDA | 931 | 930 | 119 096 / 119 168 | 0,00128460 |
| Decode, destino CPU | 100 | 100 | 11 228 / 12 800 | 0,000000954 |
| Decode, destino CUDA | 44 | 44 | 5 038 / 5 632 | 0,000000954 |

O índice C270 contém as posições de prefill 0–31, 128–159 e 160–188. A última camada só realizou o FFN na posição 188. No decode há quatro posições isoladas. O verificador autenticou os passos dos tensores, incluindo 512 B entre quartetos na tile, e as colocações CPU0–24 e CUDA25–35. Todos os coeficientes de norma eram diferentes de zero. Os controlos sintéticos distinguem uma transposição do peso, divisão pelo gamma com sinal, empates, troca de posição e uso de uma rota ainda indisponível. [Verificador](score.py) · [Testes](test_score.py)

## O que distingue as duas geometrias

No pin C269, para o peso F32 contíguo de 2880×128 na SM89, o seletor MMVF aceita até três colunas. O MMF normal recusa mais de 16. As tiles de 29/32 excedem ambos; sem dimensões adicionais de batch ou divisão do peso, alcançam o caminho de SGEMM. A implementação usa um handle que permite TF32. Esta é evidência de código; a captura não identifica a instrução ou a precisão interna adotada pelo cuBLAS naquele lançamento. A linha divergente de 32 colunas conservou os ranks 1–3 e escolheu o rank nativo 5 para o quarto. O erro máximo pré-bias nessa linha foi 0,000174642. Para reabrir, qualificar separadamente o operador largo nas 931 linhas de prefill CUDA e manter a calibração integral de todos os 3 400 quartetos. A cópia privada dos 39 parâmetros complementares permite fazê-lo sem reabrir o modelo. No pin, consultar `ggml-cuda/mmvf.cu:803–808`, `mmf.cu:168–177`, `ggml-cuda.cu:2638–2665,1798–1811` e `common.cuh:1478`, sob `ggml/src/`. [Proveniência do C269 e geometria do router](../history_lookup/b3_numeric/first_boundary/router_row/integrated/source_l25/README.md)

## Antecedente físico e condição económica

O C299/C304 já aplicou o router real de destino, com a sua própria RMS e gamma, ao **residual cru antes da atenção** de duas camadas atrás. Nos dois casos reservados, o recall sobre experts ausentes foi 66,97% e 72,84%; a precisão das leituras propostas foi 54,99% e 58,67%. Em C309 as oito execuções 153+32 pagaram o staging e validaram 33 vetores completos. A mediana do decode ficou **22,38% mais lenta no nominal e 16,58% no código**, com 377–479 leituras concluídas desperdiçadas por braço. As previsões só começaram após o prefill, para CPU2–24. C308 parou no flag OFF e não forneceu preço. A revisão aprendida C318 também piorou o decode. Esta família permanece encerrada no regime físico testado. [Estimador e cálculo](../../../tools/expert_activation_estimator.h) · [Ponto de ativação](../../../tools/expert_prediction_staging_cost.cpp) · [C304](../../C304-HELDOUT-PREDICTION-RESULT-20261007.md) · [C309](../../C309-UNTRAINED-STAGING-COST-NO-GO-20261007.md) · [C318](../../C318-LEARNED-STAGING-COST-NO-GO-20261007.md)

Neste crivo, a fonte é o operando **pós-atenção** já multiplicado pelo gamma da sua camada. A hipótese fixou remover essa escala e aplicar a do destino, também no prefill e na transição CPU/CUDA. Cada par posição/destino pede 368 640 multiplicações e acumulação nos 128 scores, além da escala e da seleção. A matriz contém 1 474 560 B e pode ser reutilizada pelas posições da tile. Latência do preditor, transporte entre backends, acertos sobre faltas reais e espera retirada ao cliente continuam sem medição. No P106, mesmo oferecendo todas as callbacks CPU gratuitamente, ainda faltavam **1,206 s** para o primeiro final de 10 s com o exterior fixo. Uma decisão sobre a conversa exige efeito fora dessas callbacks e serviço a tempo em ambos os tiers, preservando a confirmação pelo router real. [Orçamento P97/P106](../igpu_resident_rank/request_budget/device/pack_native/natural_trace/prefill_retention/repeat/README.md)

AdapMoE reutiliza gates de camadas seguintes; DALI adiciona ao input do gate uma correção média de residual calibrada e privilegia experts com mais tokens; ProMoE usa preditores treinados para emitir pedidos antecipados. Os custos e resultados desses trabalhos pertencem às respetivas plataformas. Nenhum deles valida a precisão do sinal em GPT-OSS nem o prazo de leitura no Tesy. [AdapMoE, §4.3](https://arxiv.org/html/2408.10284v1#S4.SS3) · [DALI, §4.2](https://arxiv.org/html/2602.03495v1#S4.SS2) · [ProMoE, Training of Predictor](https://arxiv.org/html/2410.22134v2)

## Reprodução

Protocolo `3e7d22f6`, verificador `21bc6936`. Duas execuções CPU, NumPy 2.5.3, um thread BLAS e 512 MiB AS, em 0,37/0,22 s com 131 684/131 600 KiB RSS. Cada uma autenticou 69 tensores C299 arquivados e leu os mesmos 39 ranges, 19 325 696 B, da colocação do GGUF autenticada anteriormente por releitura integral. Os recibos coincidem no SHA `543316d27720db89ce660dd9cad4c0aa4f5ecadebf77f03685e1ed78bcff5fc0`. A localização posterior em `f18b3e95` reabriu os mesmos parâmetros e a mesma falha em 0,29 s / 134 840 KiB. Os 39 tensores, o manifesto individual e as identidades dos experts divergentes estão apenas no destino privado do diagnóstico. [Localizador](localize.py)

```sh
env LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  timeout 90 prlimit --as=536870912 -- "$TESY_REPO/.venv/bin/python" -IB "$UNIT/score.py" \
  --part23 "$ARCHIVE/part-23" --c7 "$TESY_REPO/c7-native-placement-screen-20260927-1117utc" \
  --placement /tmp/tesy-nvme-placement-20261124-01/receipt.json --new-output-dir "$NEW"
```

Uma [calibração posterior, com identidade e protocolo próprios](tf32/README.md), recuperou os 3 400 quartetos e permitiu medir o sinal nas duas fases e nos dois destinos.
