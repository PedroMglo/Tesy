# Que acrescenta a frequência observada no próprio R0?

**NO_GO para usar a frequência acumulada do prefixo e do incremento como política fixa de expulsão nos 32 passos seguintes.** O critério congelado exige que os votos acumulados até ao fim do incremento reduzam as publicações de decode em pelo menos 10% em ambos os casos e superem as classificações do prefixo e de C286. Cada um dos 4 608 contadores ocupa 4 B numa implementação uint32 (18 432 B). O replay em Python usa objetos para simular esses contadores. [Protocolo e limites de interpretação](../warm_routes40/protocol.md)

O avaliador associa cada braço físico à família completa e exige o SHA do recibo. Confere novamente a igualdade OFF/ON dos witnesses e as escolhas individuais do serviço ON. Um voto corresponde a um dos quatro IDs reais da linha. O corte P sucede à oitava chamada de prefixo, I à nona chamada com 153 posições. A camada final só vota nas saídas efetivamente pedidas. Os 32 passos seguintes servem para validar e avaliar o ranking já fechado. O teste de causalidade troca os quatro experts de todo o decode e exige a mesma matriz de pontuações nos dois cortes. O encerramento do journal é obrigatório, incluindo para o cálculo de P.

Cada política começa na mesma cache histórica reconstruída. Preenche vagas, protege os quatro experts e paga cada falta. O empate expulsa o ID maior entre os candidatos. Para cada braço o recibo separa misses, hits, bytes lógicos destinados a CUDA, margem em cargas até ao limiar e piso de payload para recuperar as identidades de R0 no fim. Restaurar slots, gerações e estado auxiliar pode custar mais. A elegibilidade para a fixture compara as cargas da janela de 32 passos. Qualificar o produto exige medir serviço, cópias, coordenação e continuação no relógio do cliente. [Controlos por ID e recência](../warm_policy_controls/README.md) · [Origem dos scores C286](../cross_prefix_result.md)

## O que aconteceu nos dois casos

Os quatro processos físicos de 40 slots passaram o gate dos observadores. A substituição de vítimas abaixo foi **simulada** sobre as escolhas reais, a partir dos 1 440 slots observados na fronteira I. A coluna R0 conta as publicações históricas. Cada falta alternativa custa três componentes de 4 406 400 B. A ordem dos quatro ranks e os pins do target são comuns a todos os braços. [Gates por processo](../warm_route_family/README.md) · [Recibo com os top-40 e empates por camada](evidence-r1/receipt.json)

| Braço histórico, 32 passos | R0 | Votos do prefixo | Votos do prefixo + 153 | Scores C286 | Máximo para poupar 10% |
|---|---:|---:|---:|---:|---:|
| Nominal 2 ON | 1 081 | 1 517 | 1 517 | 1 434 | 972 |
| Nominal 3 ON | 1 081 | 1 517 | 1 517 | 1 434 | 972 |
| Código 2 ON | 1 308 | 1 800 | 1 546 | 1 592 | 1 177 |
| Código 3 ON | 1 308 | 1 800 | 1 546 | 1 592 | 1 177 |

Os 153 tokens novos mudaram 125 membros dos conjuntos top-40 no nominal e 249 em código, somando as 36 camadas. No nominal, a regra com o incremento fez 436 cargas a mais que R0 (+40,33%). Em código, melhorou sobre o prefixo sozinho e sobre o contador C286, mas ainda fez 238 cargas a mais que R0 (+18,20%). No fim da janela faltariam 532 e 561 identidades para recompor os respetivos conjuntos finais de R0. Só o payload dessas identidades totaliza pelo menos 7 032 614 400 B e 7 415 971 200 B. Os bytes dependem do contrafactual. Não foram medidos novos tempos de conversa ou de serviço da política.

O verificador congelado em `ffd90fac14e97fdfe0d85078e1e6849cf8d6bd12` validou novamente a família privada, os dois WRT1, o TPR1, os cortes e os inputs históricos de cada caso. A execução durou 0,92 s e usou 77 988 KiB de RSS. O SHA-256 do recibo original, antes de colocar cada top-40 numa única linha, é `3a8610fff17c23aefbf1a1d2d16e76367c78cf99a2044c8c9ab78d897ef78c09`. A política física fica NOT_RUN. Os resultados fecham esta regra no regime avaliado. [Custos das regras por ID e recência](../warm_policy_controls/README.md)

Na literatura consultada em 25/11/2026, Suram usa llama.cpp para recolher top-k com stride real. Na camada 24 de Qwen3-30B-A3B em código, a tabela 3 dá 65,9% de hits para LRU e 60,1% para LFU a 13,4% de capacidade. A medição física de 0,441 tok/s usa outro modelo, Qwen3-235B-A22B Q4_K_M, em RTX 3070 de 8 GB, 32 GB de RAM e SN530. O apêndice F atribui a diferença entre 5,3 GB/s quentes e 2,4 GB/s frios à page cache. Por isso os tempos de movimento do Tesy exigem os bytes efetivamente lidos do dispositivo. Os quatro braços C294 medem o efeito da classificação sobre o mesmo estado de 40/128 por camada do próprio target. [Suram, §§3–5, tabela 3 e correções](https://arxiv.org/html/2608.18261v1)

PDScope estuda o custo de transferir o expert residente na RAM para GPU ou executá-lo na CPU. Compara, entre outros, Fiddler e KTransformers 0.3.2 em A100 e RTX 3090, PCIe 4.0 ×16 e orçamento de GPU de 24 GB. Na avaliação principal usa quatro modelos BF16 e prompts ShareGPT de 128 a 4 096 tokens com 64 saídas. A análise de uma camada de Qwen3-30B-A3B a 1 024 entradas distingue cópia assíncrona de computação. O sinal transferível ao Tesy seria um crossover medido a partir do mesmo expert MXFP4, depois de cobrar a chegada do NVMe, as ativações e a redução na ordem do target. [PDScope, §§5.1 e 5.6](https://arxiv.org/html/2610.39216v1)

```sh
python3 -B -m unittest discover -s research/qualification-retake/warm_policy
python3 -B research/qualification-retake/warm_policy/evaluate.py \
  --family "$TESY_WARM_ROUTE_FAMILY" --family-receipt-sha256 "$TESY_FAMILY_SHA256" \
  --historical-results "$TESY_HISTORICAL_RESULTS" --new-output-dir "$NEW_POLICY_REPORT"
```

A representação compacta publicada conserva todos os scores agregados, ranks e resultados por braço. SHA-256 `a15bf10fb11c51b3879c4281145af4b21bcc18320ddde21ac63fa3bff77fa790`. A igualdade dos dois documentos JSON foi conferida campo a campo.
