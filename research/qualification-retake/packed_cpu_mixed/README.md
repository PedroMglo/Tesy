# O consumidor CUDA pode reutilizar a cópia da saída MMID

**GO para integrar o worker CPU nesta fronteira.** Duas execuções físicas da V3 no pin GGML C269 confirmaram igualdade bit a bit entre os dois layouts em todas as saídas, antes e depois da máscara, para 1, 32 e 3 posições. A referência escalar exige zero nos ranks mascarados e aceita ambos os sinais desse zero. Os comparadores foram três matrizes MXFP4 CPU densas, três vistas de um único banco com stride 13 221 888 B e uma referência escalar independente. O grafo conservou sete splits e uma única cópia de pipeline em todos os casos. [Contrato](contract.md) · [Observação pré-registada](observacao.md) · [Gates CPU e I/O](../packed_cpu_views/README.md)

## Por que a V2 falhou na cauda

A V2 terminou com `MMID scalar oracle`. Os vetores privados de 1 e 32 posições chegaram a disco e coincidem, pelo tamanho e SHA-256, com os das duas execuções V3. Têm 34 560 e 1 105 920 valores por fase, respetivamente. Na cauda de 3 posições, a V2 parou antes de gravar o vetor ou a coordenada do erro. O seu FAIL permanece no histórico. [Recibo da V2](receipts/v2-r01-native.json) · [Hashes dos vetores originais e supervisão](receipts/manifest.json)

A V3 observou a cópia já entregue ao CUDA antes de executar o MUL e releu o operando e a saída após a sincronização. Em cada uma das 18 observações por execução, os bytes recebidos na GPU coincidiam com o MMID CPU. O operando e a saída CUDA tinham o mesmo buffer e endereço. O digest do operando após MUL coincidiu com o da saída mascarada. Aplicar o predicado da V2 nesse ponto reproduziu **zero** desvios nas 1 e 32 posições, onde todos os ranks multiplicavam por um. [Recibo V3 R01](receipts/v3-r01-native.json) · [Recibo V3 R02](receipts/v3-r02-native.json)

| Componente, cauda de 3 posições | Desvios na comparação tardia, matrizes densas | Desvios na comparação tardia, vistas do pack | Primeira comparação antes → depois, em ambos |
|---|---:|---:|---|
| gate | 17 206 | 17 206 | −78,0 → −0,0 |
| down | 17 206 | 17 206 | 101,0 → +0,0 |
| up | 17 206 | 17 206 | 89,0 → +0,0 |

Todos os desvios ocorreram nos ranks de parking, 2 e 3, mapeados para os slots 36 e 37. A primeira comparação divergente na ordem original foi a de gate no layout denso, posição 0, rank 2 e linha 0 (índices com base zero). Os bits mudaram de `0xc29c0000` para `0x80000000`. A saída já mascarada era a correta. O vetor da cauda tem 103 680 valores por fase e o mesmo SHA-256 nas duas V3. Esta reprodução localiza o erro do predicado de observação no mesmo grafo. A coordenada não chegou a ser registada pelo processo histórico. [Testemunhos por componente](receipts/v3-r01-native.json)

## Percurso dos dados e recursos

Em cada grafo verificaram-se os quatro IDs ordenados por posição, tanto no argsort CUDA como no operando CPU, e todas as ativações transferidas. Os três MMID executaram na CPU, com a identidade do tensor de pesos, o ponteiro, o tipo de buffer e os strides autorizados. A cópia CPU→CUDA foi comparada com a referência antes do consumidor. No caso sem parking, os slots ativos são 39, 0, 7 e 23, rodados por posição. Após a máscara, o verificador externo releu do disco os vetores brutos e mascarados e conferiu os valores. Os commits, pins dos ELFs e hashes dos pré-requisitos, do journal e dos supervisores constam dos recibos. [Observador](mixed.cpp) · [Verificador independente](run.py) · [Manifesto](receipts/manifest.json)

| Braço | C118 (s) | Supervisor total (s) | Subprocesso incluindo build e verificação (s) | CPU no scope (s) | Pico do cgroup (B) | Máximos amostrados GPU / CPU Tctl / NVMe (°C) |
|---|---:|---:|---:|---:|---:|---|
| V2 R01 FAIL | 60,174 | 62,735 | 1,994 | 2,609 | 525 860 864 | 44,27 / 59,75 / 34,85 |
| V3 R01 PASS | 60,169 | 63,430 | 2,687 | 3,729 | 333 119 488 | 43,00 / 65,00 / 33,85 |
| V3 R02 PASS | 60,148 | 63,385 | 2,678 | 3,759 | 335 052 800 | 43,57 / 66,00 / 33,85 |

Cada C118 recolheu 61 amostras sob alimentação AC e perfil performance. O supervisor aplicou o teto de 1 GiB, com swap zero e sem OOM nos três braços. O uso total de VRAM amostrado atingiu 104 MiB na V2 e 110 MiB em ambas as V3 na RTX 4060 Laptop. A telemetria do operador registou 7, 10 e 10 amostras, respetivamente. As durações incluem os custos da fixture, da compilação local e da verificação conforme o âmbito de cada coluna. A referência do arquivo privado para estes raws é `qualification-20261124-nvme-01/part-14`. [Índice dos lotes privados](../private_archive/README.md)

Os pesos e as ativações desta fixture são sintéticos. O PASS qualifica os operandos e as transferências observadas no grafo C269. A entrega a um slot pelo worker C291, a paridade de logits do modelo e o efeito no prefill/decode de uma conversa 120B têm gates próprios. M3 continua PARTIAL e M4 NOT_MET.
