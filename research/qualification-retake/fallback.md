# C322 · custo de satisfazer um miss com uma segunda leitura

**NO_GO no perfil C305 com staging e predictor ativos.** Nos quatro pares físicos, abandonar uma leitura especulativa em curso e pedir os bytes de novo atrasou tanto o decode como o pedido de trabalho fixo. Uma fila auxiliar continua a poder servir um expert já pronto. A implementação que começava uma segunda leitura quando o expert ainda estava em voo pode ser retirada da lista de candidatos a confirmação neste regime.

## Reprodução sem modelo

Em 24 de novembro de 2026 foram verificados 690 ficheiros da captura científica local de 9 de outubro, com 576 434 276 bytes. A árvore coincide integralmente com os tamanhos e SHA-256 do manifesto. O avaliador C322 voltou a validar, nos oito braços, os IDs, o estado inicial dos pares, as 33 linhas completas de logits finitos por braço, o perfil, as bibliotecas carregadas, a conclusão e os limites de recursos. Cada resultado integral por braço coincidiu com a análise original. O recibo novo publica apenas os valores agregados e as identidades científicas.

| Identidade | SHA-256 |
|---|---|
| GGUF original identificado nos manifestos físicos | `582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d` |
| Biblioteca C305 de controlo | `d8460ecec23274ebba145530a1aacdb2746ee94969aba40b8b2beb38e0bb90d4` |
| Biblioteca com fallback | `49128363572257bdec05591f31e71e18d0ecce6502c9da9ebf949cb711835dc3` |
| Patch de `src/c305-cpu-stage.h` | `c20068f40ebd9f121c234db91305685c6d8fbdb8d8936416d5efab2ae3d4228b` |
| Protocolo | `f96ec8547ff60d8d5ef18af2d263e2b62a5e00ab46f329bcbbbae699ddfd96d5` |
| Manifesto raw | `5baf5e867e8ee6ab04979da25154ee958f0870289cf969fbb3cee325c1f3c34b` |
| Avaliador congelado | `2f27d12f99a97ec150e21e6c04232a81e48a47ace53c454dfd7fb7d7c252fdd9` |
| Recibo agregado reproduzido | `b06183b18f9c8cfd93f5e8b2cdcbde7e907a38fcb83c02f49fa4953d5ce8293d` |

Base C305 `c94780b12820c7b3fb20f2a9acf38bb27506c6ae`, árvore `e418713c063a33214d5bf75f3ff25b40090ab7a1`. Os 33 ficheiros pinados de código, artefactos e entradas foram reconferidos na cópia científica e na instalação Tesy existente. Esta reprodução lê o raw em modo de leitura e usa as dependências do avaliador já presentes na main. O custo físico pertence à execução histórica de 1 202,782 s, com oito braços, sem repetições após falha, cap de 18 GiB e swap do serviço a zero. A captura excedeu a projeção de 512 MiB em 39 563 364 bytes. A auditoria nova dispensou GPU e forwards.

Para reproduzir, indicar em `C322_CHECKOUT` a raiz da cópia que contém a ferramenta histórica e a campanha. A saída deve ser um diretório novo, fora dessa cópia. Requer Python e NumPy, como o avaliador da main.

```sh
python3 -B research/qualification-retake/fallback_cost.py \
  --checkout "$C322_CHECKOUT" --new-output-dir "$OUT_C322_NOVO"
sha256sum "$OUT_C322_NOVO/receipt.json"
```

## Resultado por braço

MEDIDO no portátil, REPRODUZIDO a partir da captura. Em cada célula, os segundos seguem a ordem controlo → candidato indicada pelos números de braço. Os ganhos usam 100 × (controlo − candidato) / controlo. O relógio começa depois do prefixo, cobra o prefill incremental de 153 tokens e os 32 passos fornecidos. O decode inclui o cleanup das leituras especulativas. As comparações usam o tracer desligado.

| Caso | Par | Prefill (s) | Decode com cleanup (s) | Total (s) | Ganho decode | Ganho total |
|---|---|---:|---:|---:|---:|---:|
| código | 1 → 2 | 15,945 → 15,960 | 11,451 → 12,496 | 27,395 → 28,456 | −9,13% | −3,87% |
| código | 4 → 3 | 16,037 → 15,864 | 11,469 → 12,527 | 27,505 → 28,391 | −9,23% | −3,22% |
| nominal | 6 → 5 | 9,893 → 9,888 | 9,828 → 10,972 | 19,721 → 20,860 | −11,64% | −5,78% |
| nominal | 7 → 8 | 9,850 → 9,888 | 9,806 → 10,838 | 19,657 → 20,726 | −10,52% | −5,44% |

O avaliador executável C322 exigia os quatro sinais de decode positivos, mediana de ganho em decode de pelo menos 3% e mediana total de pelo menos zero em cada caso. Devolveu `STOP_CANDIDATE_HARM_OR_GATE_MISS`. As medianas nominais de prefill, decode e total são −0,17%, −11,08% e −5,61%. Em código são +0,49%, −9,18% e −3,55%. Também se perdem as vias globais e de fase do avaliador C318 nos tempos observados, e o custo nominal excede a proteção de 5% se código for o caso primário. Os cortes condicionais C318 de 17,62% e 18,02% pertencem ao contraste com R0 daquele estudo.

O controlo esperou por uma leitura em voo 271 e 277 vezes em código e 223 e 231 vezes em nominal. O candidato registou zero esperas desse tipo nos quatro braços. Expiraram leituras em execução 337 e 350 vezes em código e 284 e 281 vezes em nominal. O contador de bytes de leitura atribuído ao processo pelo kernel aumentou 2,98–3,29% por par. Para atribuir a penalização à contenção do dispositivo seria necessário identificar serviço e sobreposição no caminho crítico. Estes contadores medem outra grandeza que o tráfego físico do NVMe.

## Consequência para a decisão de produto

O controlo deste ensaio usou C305 com staging e predictor ligados. R0 operacional mantém o seu próprio controlo. O resultado fecha a variante de duplicação em C305. A continuação sem duplicar bytes no #44 ainda precisa de identificar serviço útil que um worker consiga adiantar antes da barreira numa única conversa e de cobrar o seu custo. O #44 já demonstrou que o prefixo do journal de staging é contíguo sob o mutex. Para medir o trabalho adiantável no caminho crítico faltam a identidade do worker, o redispatch e park/wakeup, o serviço, a última barreira e o drain. A exatidão coberta é a destes oito braços com tokens fornecidos. A qualificação de respostas naturais, M3 PARTIAL e M4 NOT_MET conservam os seus gates.
