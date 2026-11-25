# Elidir pesos com ativação exatamente zero na projeção down

**NO_GO como intervenção isolada no regime de serviço R0 estudado.** No prefill nominal de C135, o trabalho residual ocuparia pelo menos **4,341 s** mesmo com uma das três leituras inteiramente grátis à escolha em cada admissão e com quatro workers sempre disponíveis. O pedido dispunha de **2,427104 s** quando se concede decode das suas 47 saídas a exatamente 6 tok/s e se antecipa todo esse crédito até ao primeiro conteúdo. O piso excede o orçamento em **1,914 s**. Um cálculo por componentes que apaga especificamente down dá um piso maior de **4,981 s**. O resultado dispensa estimar a frequência de zeros ou capturar outro forward. [Protocolo](protocol.md) · [Recibo reproduzido](evidence/receipt.json) · [Relógios C135](../prefill_read_floor/README.md)

## Prefill 5 + 148 do próprio C135

| Chamada | Gerações | Serviço READ observado gate/down/up (worker-s) | Piso de parede ao apagar o READ mais lento de cada geração | Piso ao apagar down |
|---|---:|---:|---:|---:|
| 5 | 45 | 0,218 / 0,161 / 0,210 | 0,087989 s | 0,106924 s |
| 148 | 1 177 | 10,133 / 8,123 / 9,366 | 4,253008 s | 4,874297 s |

A ordem dos papéis é verificável nos pins C122 `ba058e62` e C294 `237e3b87`. Em ambos, `src/models/openai-moe.cpp` linhas 47–49 cria gate, down e up por essa ordem e `src/llama-model.cpp` linha 1772 delega a criação dos tensores da cache. O manager acrescenta cada componente ao vetor e percorre-o em ordem. No C122, ver `src/llama-moe-stream.cpp` linhas 307 e 446–490. No C294, ver linhas 220 e 361–367. Por geração, permitir que a leitura mais lenta se torne grátis cobre qualquer redução parcial de down quando os READ dos restantes pesos conservam a duração original. Descontou-se 1 µs de resolução a cada um dos dois READ mantidos, com mínimo zero. Dentro de cada chamada, a soma de serviço restante dividida por quatro limita inferiormente a ocupação de parede. As duas chamadas externas são sucessivas. Nenhum custo de cálculo, publicação ou coordenação é necessário para este limite. [Emissor C122](../../../patches/C122-warm153-decode-trace.patch) · [Controle C135](../../C135-C136-SLOTS40-RESIDUAL-DECODE-20260929.md)

**Cenário de bytes.** As 1 222 admissões custaram 16 153 862 400 B de payload lógico, dos quais 5 384 620 800 B em down. A 4,5 GB/s úteis, 2,427104 s acomodariam 10 921 968 000 B. Seria preciso suprimir pelo menos 5 231 894 400 B, **97,1637% de down**. Apagar a matriz down inteira em todas as admissões deixaria 10 769 241 600 B e só 33,9392 ms de margem para tudo o resto. A taxa é um cenário de leitura sequencial. Os READ do trace incluem serviço do caminho de E/S original. O protocolo mantém a geometria de tiles e as admissões do GGUF original. [Cenário de banda](../prefill_oracle40/README.md)

## Decode de 32 passos fornecidos em C294

| Braço trace-ON | Faltas CPU / CUDA | Piso só READ a 1× (s) | C295 exterior fixo (s) | Exterior + READ a 0,8× / 1× / 1,2× (s) |
|---|---:|---:|---:|---:|
| nominal 2 | 762 / 319 | 4,386072 | 1,773408 | 5,282266 / 6,159480 / 7,036694 |
| nominal 3 | 762 / 319 | 4,383545 | 1,830919 | 5,337755 / 6,214464 / 7,091173 |
| código 2 | 927 / 381 | 5,289265 | 1,817114 | 6,048526 / 7,106379 / 8,164232 |
| código 3 | 927 / 381 | 5,304100 | 1,829011 | 6,072291 / 7,133111 / 8,193931 |

Cada braço contém 32 × 36 grupos sucessivos com até quatro faltas do mesmo top-4. Cada geração conserva a sua cadeia de dois READ. A soma do máximo por grupo dá o piso de parede da coluna só READ. O cenário C295 conserva trabalho exterior ao serviço no relógio do próprio braço e concede gratuitamente os SET e o overhead dos workers nos dois tiers; o simulador e a soma independente coincidem. O limite para 6 passos/s é **5,333333 s**. À escala 0,8, o nominal 2 mantém 51,068 ms antes de cobrar quaisquer custos adicionais, o nominal 3 excede o limite em 4,422 ms e os dois braços de código excedem-no em 715–739 ms. À escala 1× os quatro excedem o limite. Se *todo* o trabalho exterior se tornasse gratuito, os quatro pisos só READ a 1× ficariam abaixo do limite. A decisão do decode depende da conservação do trabalho exterior especificada em C295. Estes braços não incluem requests de cliente ou novos resultados naturais. [Cadeias de componentes](../component_ready_bound/README.md) · [Simulador C295](../../../tools/expert_prediction_scenario.py)

## O que uma observação de zeros mediria

A entrada da projeção down é `ffn_moe_swiglu_oai`. O pin C269 `d0ebfbcc` cria-a em `src/llama-graph.cpp` linhas 2112–2117 e consome-a na linha 2139. O tensor `ffn_moe_out`, na linha 2233, já contém a contribuição final reduzida dos ranks. O kernel CPU usa gate limitado superiormente, up saturado a [−7,7], e calcula `(x / (1 + exp(−1,702·x))) · (y + 1)`; a operação permite zeros, mas não impõe uma fração de zeros como ReLU. Em MXFP4, cada linha de 2 880 pesos contém 90 blocos de 32 elementos com 17 B por bloco. Para omitir uma faixa de 32 entradas reduzidas em todas as 2 880 linhas de saída, 48 960 B de payload, todos esses multiplicadores têm de ser zero em todas as posições e ranks consumidores daqueles pesos. Um consumidor posterior com ativação diferente exige que a cache saiba o que falta e reconstitua os bytes. Uma execução exata também tem de respeitar as operações observáveis do kernel, incluindo quantização de ativação e ordem de redução.

Os manifestos C265, C266 e C270 cobrem referências autênticas na entrada da FFN, routing, pesos de mistura, máscaras e/ou saída; nenhum dos três conserva valores da ativação pós-SwiGLU que alimenta down. A fixture CPU0 de C269 foi validada contra os 92 160 valores finais de uma tile do FFN. A densidade real de blocos omissíveis permanece **DESCONHECIDA**. Reabrir esta linha exigiria outra premissa material, como reduzir substancialmente o serviço de gate/up que permanece obrigatório, mudar as admissões iniciais pagando o seu custo ou demonstrar que a nova ordem/layout acelera os READ mantidos. Uma captura isolada de zeros não altera o limite deste regime. [C265](../../../results/c265-native-probs-alias-repair-20261004/raw-manifest.json) · [C266](../../../results/c266-new-shape-native-canonical-reference-20261004/raw-manifest.json) · [C270](../../../results/c270-last-use-ordered-fidelity-20261004/raw-manifest.json) · [Camada CPU0](../packed_real_layer/README.md)

## Reprodução sem modelo

Protocolo congelado em `acc9e2a1f10d5a7cf14e0c3ed9468b31c84b8b65`; programa e checkout limpa `5491680c8a62da292ae7138453d15121cf94232a`. R01 atingiu o cap de espaço de endereçamento de 384 MiB ao analisar os dados. A tentativa de escrever o erro no processo já sem espaço também falhou, deixando o recibo original vazio. A execução durou 0,67 s com 88 520 KiB de RSS máxima. A inspeção sem dados identificou 227 912 KiB do catálogo de locale mapeado no processo. R02 e R03 mudaram apenas o locale e a codificação do processo. Duraram 1,04 e 1,01 s, com 92 324 e 92 608 KiB de RSS máxima. Os dois recibos de 7 486 B são iguais byte a byte, SHA-256 `4421bc55654ef3452c646591c9c1ae07773337997032b39a23f8546ecad7037b`. Não houve leituras de pesos, GPU nem forwards. [Falha R01](evidence/r01.json) · [Reprodutor](screen.py)

Fixar `W` na checkout científica e `C7` na raiz do laboratório que guarda os dois conjuntos originais. Usar um `NEW` ainda inexistente a cada execução. Para reproduzir a invocação de R01, omitir do comando as três atribuições de locale e usar o locale original da estação.

```sh
env LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 -B "$W/research/qualification-retake/zero_down/screen.py" --repo "$W" \
  --trace "$C7/results/c135-slots40-warm153-trace-20260929T2205Z/raw/c135-c75-slots40-warm153.expert.trace" \
  --raw-dir "$C7/results/c294-feature-ready-service-window-20261006/raw" --new-output-dir "$NEW"
```
