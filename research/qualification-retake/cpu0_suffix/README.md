# Quanto dura o FFN depois da remap ativa na camada CPU0?

**INCONCLUSIVE_OBSERVER_OR_DISPERSION.** Na mesma tile real de CPU0, os quatro sufixos medidos em ON ficaram entre **18,604 e 20,098 ms**, com mediana de **19,134 ms**. O primeiro par teve um quociente de duração do grafo ON/OFF de 0,8253, abaixo de 0,85. Todos os quatro sufixos ficaram na banda prescrita em torno da mediana ON. A neutralidade temporal exigia também que todos os pares respeitassem a banda de 0,85 a 1,15. [Pré-registo](protocol.md) · [Avaliação reproduzida](physical-r01/receipt.json)

| Par | Braços e ordem | Grafo OFF (ms) | Grafo ON (ms) | ON menos OFF (ms) | ON/OFF | Sufixo medido ON (ms) | Intervalo do sufixo OFF (ms) |
|---|---|---:|---:|---:|---:|---:|---:|
| 1 | 0 OFF, 1 ON | 59,129 | 48,798 | −10,331 | 0,8253 | 18,604 | [0; 59,129] |
| 2 | 2 ON, 3 OFF | 47,268 | 46,370 | −0,898 | 0,9810 | 18,610 | [0; 47,268] |
| 3 | 4 ON, 5 OFF | 45,476 | 47,358 | +1,882 | 1,0414 | 20,098 | [0; 45,476] |
| 4 | 6 OFF, 7 ON | 50,847 | 49,368 | −1,479 | 0,9709 | 19,659 | [0; 50,847] |

**MEDIDO.** Cada `graph_compute` do FFN e a sua sincronização foram cronometrados com `CLOCK_MONOTONIC`. ON colocou uma única marca logo depois do retorno da remap da wave zero, numa equipa de oito threads. O intervalo até ao fim do grafo inclui o resto da wave ativa, as sete waves estacionadas e a redução. Em OFF existem apenas as extremidades do grafo. As diferenças da quinta coluna misturam efeito do observador e variação entre processos. O custo isolado do observador e a duração do sufixo OFF permanecem desconhecidos. Uma futura observação do retorno sob uma fronteira independente poderá reduzir esse intervalo. O resultado não identifica um piso de cálculo no caminho crítico do C135. [Fronteira no código](source.md)

Cada um dos oito processos iniciou o manager C291 DENSE vazio em CPU, com quatro workers, a mesma captura de router de 153 posições e a mesma tile FFN de 32 posições. Os oito grafos tinham 110 nós, 24 MMID e um split. O `cb_eval` ficou desligado nos oito processos. As **oito saídas reproduziram o gold C266** byte a byte, **92 160 F32 / 368 640 B por braço**, SHA-256 `bf0391c5e7aad2aa22c730d56c07213fadcd0db1b7801d5dd58e1533f9aaba24`, total **2 949 120 B**. A conservação do trabalho prevê cinco cargas e quinze SET por processo, 528 875 520 B de leituras alinhadas e 528 768 000 B de payload na família. Os contadores de I/O físico por expert e o tempo de serviço dos SET não foram instrumentados. O pack já preparado foi utilizado sem abrir o GGUF nem utilizar GPU compute. [Controlo da camada](../packed_real_layer/README.md)

A C118 recolheu 61 amostras em 60,185 s. O supervisor mediu 61,880 s de parede na família inteira e três amostras durante o período depois da C118. O cgroup de 4 GiB atingiu 198 983 680 B, com pico de swap zero e zero filhos no fecho. A checkout e o build registam `e6e63160465a11fc4404809d7e217fe2a761db1b`, árvore `a407df0ea40d59cdfb41409ea6cad6cc46abe10c`. O recibo terminal das oito execuções e a decisão sobre o observador ficam ambos preservados. M3 permanece PARTIAL e M4 NOT_MET.

## Reprodução sem inferência

O compactador autentica o build, o recibo terminal, os stdout e stderr, as oito tiles e a telemetria arquivada. Reaplica o avaliador congelado aos relógios de cada processo. Em caso de falha da família, publica apenas as fases preservadas. A argumentação temporal é específica desta unidade. Uma falha do caminho de leitura da C118 na primeira execução do compactador foi corrigida para usar a localização documentada `raw/`. Nenhum braço foi repetido e nenhum raw foi alterado.

```sh
study=research/qualification-retake/cpu0_suffix
python3 -IB "$TESY_CHECKOUT/$study/compact.py" --repo "$TESY_CHECKOUT" \
  --raw-root "$TESY_CPU0_SUFFIX_R01" --build-dir "$TESY_CPU0_SUFFIX_BUILD" \
  --receipt-sha256 7dd15efa987d9bdf1e434e36e0aa5c47b72eb29ba6a6cdcb14e71e26ca0357bd \
  --new-output-dir "$NOVO_COMPACTO"
```
