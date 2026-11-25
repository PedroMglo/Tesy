# A história fornece poucos blocos verificáveis de oito posições

**NO_GO para a cópia de um segmento contíguo da história com os custos AR/B8 de C247.** Mesmo escolhendo com conhecimento do futuro quando usar AR, onde copiar e quantos tokens aproveitar, o ganho mediano fica em **5,45% no código** e **4,77% no planeamento de rota**. Os dois pares de cada caso têm ganhos positivos, mas ambas as medianas ficam aquém dos 15% exigidos. Na âncora nominal, o melhor plano usa só AR nos dois pares. A triagem termina antes de implementar um proponente causal. M3 continua PARTIAL e M4 NOT_MET. [Protocolo](protocol.md) · [Recibo dos seis pares](evidence/receipt.json)

## O que era possível copiar

O target confirmou as mesmas 32 saídas greedy nos 12 braços originais. A âncora inicial saiu do prefill e fica fora desse denominador. Em cada posição, o oráculo pode escolher qualquer segmento já inteiramente disponível no prompt e na continuação confirmada, mesmo sem encontrar um n-grama que indique a sua origem. Uma verificação aceita até sete tokens copiados mais um token do target, corretivo ou seguinte. A contagem na tabela é um **limite combinatório** para esta fonte e esta janela de 32 saídas.

| C247 | IDs no prompt | Posições com sete IDs copiáveis, em 32 | Mínimo de chamadas só B8 | Tokens copiados no testemunho / tokens do target | Saídas por verificação | Linhas de logits cobradas |
|---|---:|---:|---:|---:|---:|---:|
| Código RLE | 135 | 1 | 14 | 18 / 14 | 2,29 | 112 |
| Planeamento de rota | 184 | 3 | 14 | 18 / 14 | 2,29 | 112 |
| Âncora nominal | 2197 | 0 | 17 | 15 / 17 | 1,88 | 136 |

As três posições de rota com sete IDs copiáveis podem ter saídas sobrepostas. A programação dinâmica conserva só transições concatenáveis e cobra oito linhas mesmo na última verificação. A aceitação aqui é a de um testemunho offline. As posições de origem e os limites de cada ação estão no recibo, sem o texto do prompt. [Avaliador](screen.py) · [Testes de enumeração e causalidade da origem](test_screen.py)

## Ganho ao escolher entre AR e B8

Os números dos braços seguem a ordem original AR–B8–B8–AR. As duas primeiras durações são MEDIDAS em C247. Na duração híbrida, o custo por AR é a duração das 32 chamadas AR dividida por 32 e o custo por B8 é a duração das quatro verificações perfeitas dividida por quatro. Concedemos consulta, escolha, reparação de KV e recomputação gratuitas. O resultado é **condicional a essas médias**.

| Caso | Braços AR / B8 | AR32 / quatro B8 perfeitos (s) | Ótimo híbrido AR + B8 | Tokens copiados aceites | Linhas de logits | Tempo híbrido (s) | Ganho |
|---|---|---:|---:|---:|---:|---:|---:|
| Código RLE | 1 / 2 | 12,901 / 9,635 | 18 + 2 | 12 | 34 | 12,075 | +6,41% |
| Código RLE | 4 / 3 | 11,807 / 9,684 | 24 + 1 | 7 | 32 | 11,276 | +4,50% |
| Planeamento de rota | 1 / 2 | 10,424 / 8,461 | 24 + 1 | 7 | 32 | 9,933 | +4,71% |
| Planeamento de rota | 4 / 3 | 10,453 / 8,433 | 24 + 1 | 7 | 32 | 9,948 | +4,83% |
| Âncora nominal | 1 / 2 | 9,784 / 8,348 | 32 + 0 | 0 | 32 | 9,784 | 0% |
| Âncora nominal | 4 / 3 | 9,862 / 7,696 | 32 + 0 | 0 | 32 | 9,862 | 0% |

O C247 tinha medido ganhos medianos de 21,65% e 19,08% com quatro verificações perfeitas em código e rota. O C258 mediu outra proposta, produzida por um head EAGLE3 real. Aí foram necessárias 12 e 15 verificações, respetivamente, com 20 e 17 tokens propostos aceites e ganhos totais de −20,83% e −59,61%. O head gerava tokens fora das sequências copiáveis e pagava o custo de draft, da recomputação e da verificação. Esta unidade testa a hipótese independente de dispensar esses custos através da cópia. [C247](../../C247-B8-AMORTIZATION-RESULT-20261004.md) · [C258](../../C258-REAL-HEAD-DEVELOPMENT-RESULT-20261004.md)

## Antecedente e limites

Yang et al. avaliaram LLMA com documentos recuperados e sessões anteriores como referência. Usaram LLaMA FP16 de 7B e 13B numa V100 de 32 GB e 30B em quatro V100 de 32 GB, batch 1 e greedy. Os tempos reportados somam o decode de 100 exemplos e são médias de três execuções. Na simulação guiada descrita na secção 3.2, as saídas de davinci-003 e as referências determinaram os passos executados por LLaMA. A diferença testável aqui é a sobreposição entre os IDs que o próprio GPT-OSS-120B confirma e a sua história efetivamente disponível. O custo de verificar oito linhas vem do portátil. [Artigo original, secções 3.2–3.4](https://arxiv.org/pdf/2304.04487)

Uma trajetória com mais repetições, uma referência adicional disponível causalmente ou um verificador com outra economia pode mudar a decisão. Os custos nas posições individuais e nas uniões de experts de propostas rejeitadas ficaram por medir. Há igualdade dos IDs greedy nos seis pares C247 observados. Ficam por demonstrar os logits completos entre geometrias, a distribuição de sampling e o custo de um pedido natural com o validador e relógios de produto. A âncora nominal tem 32 posições fornecidas e não mede as 47 saídas da conversa nominal E20.

## Reprodução

Os dois replays correram na checkout limpa `11f1f7211faf472ba97abcf9bb1341c01b4a6caa`, árvore `5a7f03c5278fa158f4f77a4acc355130800b92b0`. Autenticaram a fixture C244 e os 96 ficheiros da árvore de C247 (9 327 695 B). Para os 12 processos, conferiram os IDs de entrada, as entradas teacher-forced, os 32 argmax e as linhas materializadas. Usaram CPU, zero GPU e zero novos forwards. A r01 levou 0,18 s com 22 684 KiB de RSS máxima. A r02 levou 0,08 s com 23 896 KiB. Os recibos têm 40 043 B e são idênticos byte a byte, SHA-256 `aa89de5ea321efdae6e776764d597c298c2d6a3f9887dd5366e6563f59b403ad`. [Recibo publicado](evidence/receipt.json)

```sh
python3 -B research/qualification-retake/history_lookup/screen.py \
  --raw-dir "$TESY_C247_RAW" --new-output-dir "$DESTINO_NOVO"
```

A opção sem `--raw-dir` identifica expressamente o âmbito de comprovação pelos recibos públicos históricos. As duas confirmações acima usaram os originais privados.
