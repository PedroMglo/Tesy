# Quanto pode o despacho mudar o prefill da conversa?

**NO_GO condicionado no C135 para ganhar 1,052 s só por reordenar os quatro workers dentro da chamada de 148. INCONCLUSIVE para alterar a duração do serviço das leituras no NVMe.** A exploração retém todas as 1 177 gerações, o routing do target, a ordem de waves, as barreiras entre tiles/camadas e o trabalho do controlador fora de WAIT. A hipótese mais permissiva abre todas as leituras de cada tile×camada quando aparece a sua primeira DEMAND. O máximo de alívio no replay é 0,693029 s. O teto continua abaixo da escala requerida mesmo concedendo custo zero aos três SET por carga na agenda com liberação original. [Recibo](evidence-20261125-r1/receipt.json)

| Call 148 C135, trace ligado | Alívio máximo no relógio da call com non-WAIT fixo | Com interior observado dos callbacks também gratuito |
|---|---:|---:|
| 1 177 serviços, liberados no primeiro enqueue da sua geração | 0,691940 s | 0,693118 s |
| Todos liberados na primeira DEMAND do respetivo tile×camada | 0,693029 s | 0,693118 s |
| Enqueue original e todos os TENSOR_SET_BEGIN→RETURN gratuitos | 0,946270 s | 0,947449 s |
| Controlo do cálculo #45, suprimir as 184 recargas entre tiles | 1,367310 s | 1,368083 s |

O segundo turno natural E20 mediu primeiro conteúdo final aos 21,442675606 s no cliente, prefill de 11,330690 s e decode de 10,390735 s no servidor. Na hipótese extrema de retirar todo o decode e conservar o resto do trabalho, ainda faltam 1,051940606 s para o alvo de 10 s. Arredondámos esse valor para cima, a 1 051 941 µs, ao confrontar a escala com C135. Este último é um journal histórico noutro processo e build. A conta analisa apenas a call de 148. A intervenção mantém o retorno de 5, o intervalo entre chamadas, o restante processamento do pedido e a entrada no decode. Uma decisão operacional requer pares em R0 contemporâneo, nominal e código, com trace desligado, proteção do decode e conclusão validada. [Conversa natural](../nvme_conversation/README.md)

### O que conserva o limite

O script emparelha camada, expert, slot e geração da primeira admissão e os três READ/SET em cada serviço. Há 761 cargas CPU e 416 CUDA em 147 tile×camadas com cargas. Nas waves 0, 1, 2 e 3, as esperas observadas somam respetivamente 5,589512, 1,781737, 0,182250 e 0,003273 s. Cada consumidor que espera impõe um limite até ao WAIT_END. Para um preload já READY no primeiro uso, o limite conservador é o fim da espera ou o início do callback seguinte. Os tempos LOAD_BEGIN→LOAD_END são serviço por worker, incluídos atrasos de contenção. LOAD_END antecede commit. Os deadlines concedem entrega no limite sem custos de publicação, pin, transferência de staging, wakeup ou drain adicionais.

O solver pinado no #45 soma durações de jobs inteiramente contidos em cada intervalo, divide o volume por quatro e incorpora o maior serviço individual e as arestas de precedência do controlador. O resultado é uma duração **mínima**, mesmo que a atribuição ideal não seja executável. Admite serviços sobrepostos até à capacidade do conjunto e não fixa worker individual ou FIFO. Na primeira linha, o serviço só fica elegível depois de existir a geração no primeiro enqueue. Na segunda linha, permite mesmo ler antes de o R0 lhe atribuir geração e destino físico, já desde a primeira DEMAND do router desse tile×camada. Concede antecipadamente a identidade das faltas que ocorreriam e staging ilimitado gratuito, sem crédito por liberar antes desse ponto ou atravessar uma camada ou tile. Na terceira, retirar a duração do SET inclui o que a função de cópia reportou até ao retorno, inclusivamente espera interna.

Os restantes LOADs não podem ficar mais curtos que a duração observada menos a resolução de 1 µs, exceto na sensibilidade explicitamente parametrizada. As margens não modelam como o reordenamento alteraria a contenção no NVMe, RAM, PCIe, a duração dos outros workers, os kernels e o controlador. CPU e CUDA partilham o dispositivo de leitura. Os 18,037391 + 9,585647 **worker-s** em READ e os 0,477089 + 0,497126 worker-s em SET são somas de intervalos que podem coincidir. O processo computa a parede por restrições temporais, sem somar worker-s ao relógio cliente. Os hashes conferem o journal e o validador antes do replay, e os dois tetos já publicados para as 184 têm de reproduzir. [Fonte pinada do solver](https://github.com/PedroMglo/Tesy/blob/83146dade3f90235775e4a31a8d3d8ccae3476a7/research/prefill-slot-proof/critical_intervals.py)

### Serviço que merece uma prova

Reduzir uniformemente apenas a duração READ de cada uma das 1 177 gerações, no seu enqueue original e com despacho ideal, eleva o teto à escala de 1 051 941 µs pela primeira vez a **5,1150%** na grelha de 1 ppm. A 5,1149% o teto era 1 051 940 µs. A 5,1150% é 1 051 946 µs. Essa diferença inclui relaxação de despacho e arredondamento favorável em cada job. A média da amostra e as reduções na cauda têm implicações diferentes em cada deadline.

O primeiro teste é mudar apenas a ordem de leituras já elegíveis de uma wave, mantendo quatro workers, os três preads O_DIRECT consecutivos de cada expert e os tensores do GGUF original. Ordenar por offset **no ficheiro** pode mudar a latência física das mesmas requisições no NVMe. Comparam-se FIFO e ordenação dentro do lote de demandas, com os preloads da mesma passagem nas posições originais, incluindo o custo de ordenar. As primeiras waves 0 com pelo menos oito demandas novas, de ordem diferente da ordenada, são CPU14 e CUDA25 no tile 0. As duas juntas têm 17 demandas e 15 preloads. Uma comparação de serviço loader-only mede leitura por identidade, barreira da última demanda, drain e setores do dispositivo. A transferência a todos os tiles exigiria distribuição de reduções por identidade, posição nas dependências e uma prova integrada. C125B já encerrou a intervenção que mudava a concorrência de componentes de quatro para doze threads no stream de decode. C293 já mediu a alteração do formato de armazenamento. [C125B](../../C125B-COMPONENT-IO-RESULT-20260929.md) · [C293](../../C293-INTEGRATED-EXPERT-STORE-COST-NO-GO-20261006.md)

No #45, a antecipação para um destino físico fixo fica limitada a 0,984452 s e a remoção direta das 79 recargas da própria wave a 0,794992 s sob o modelo de serviço fixo. No #48, prepin com **44** slots tem tetos de 0,653145/0,660163 s nos dois C163 ON, com 50 serviços removidos e 851 retidos. C280 mediu ganhos de prefill R0→E de 13,13% nominal/22,16% código no perfil geométrico R2, mas os dois decodes nominais regrediram mais de 10%, excedendo a proteção. C261 observou as 184 recargas históricas e as admissões mínimas de capacidade; estes tetos distinguem as contagens da dependência que o pedido aguardava. [#45](https://github.com/PedroMglo/Tesy/pull/45) · [#48](https://github.com/PedroMglo/Tesy/pull/48) · [C261](../../C261-SLOTS40-PREFILL-OPPORTUNITY-20261004.md) · [C280](../../C280-R2-CAUSAL-COST-NO-GO-20261005.md)

### Reproduzir

O cálculo é **exploratório**. A hipótese surgiu ao comparar o recibo natural com a evidência já publicada. Em clone completo, apontar para uma checkout do #45 em `83146dade3f90235775e4a31a8d3d8ccae3476a7`. O script confere HEAD e SHA-256 de todas as cinco fontes importadas. O processamento original consumiu 0,47 s, 76 916 KiB de RSS, uma leitura do journal mais validação e zero modelos/GPU. O diretório de saída deve ser novo. A opção `-B` protege a checkout de dependências contra escrita de bytecode.

```sh
python3 -B research/qualification-retake/prefill_dispatch/dispatch.py \
  --pr45-checkout "$TESY_PR45_CHECKOUT" --trace "$TESY_C135_TRACE" \
  --new-output-dir "$NEW_OUTPUT"
cmp "$NEW_OUTPUT/receipt.json" research/qualification-retake/prefill_dispatch/evidence-20261125-r1/receipt.json
```
