# Os mesmos 353 experts dão margem nos dois relógios?

**A 1×, NO_GO. A 0,8×, há apenas margem formal.** No T2 nominal da parte 40, a melhor seleção de 353 vítimas de T1 produz simultaneamente pisos de **9,451459 s** até ao primeiro conteúdo final, **3,754172 s** no relógio nativo dos 47 tokens e **9,0022752 GB** de payload obrigatório do prefill. O orçamento M4 de prefill desta sessão admite 10,690306614 GB a 4,5 GB/s. Cobrar o requisito de 6 tok/s à mesma seleção conserva, portanto, a margem da sensibilidade de 0,8×. Com os READ ao preço observado na captura, nenhuma das 396 divisões admissíveis da capacidade consegue passar os dois relógios. O primeiro conteúdo final já excede 10 s. [Pré-registo](protocol.md) · [Recibo dos replays](evidence/receipt.json)

| Preço de READ | Seleção com conhecimento de T2 | Piso primeiro final (s) | Piso decode (s) | Orçamento residual primeiro final / decode (s) | Prefill (GB) |
|---|---|---:|---:|---:|---:|
| 1× | Melhor primeiro final e melhor conjunto | 10,128999 | 3,966271 | −0,128999 / +3,867062 | 9,0022752 |
| 1× | Melhor decode | 10,147396 | 3,939055 | −0,147396 / +3,894278 | 9,0948096 |
| 0,8× | Melhor primeiro final e melhor conjunto | 9,451459 | 3,754172 | +0,548541 / +4,079161 | 9,0022752 |
| 0,8× | Melhor decode | 9,466184 | 3,732355 | +0,533816 / +4,100979 | 9,0948096 |

Cada linha usa uma única seleção nos dois relógios e no volume. A K353, a seleção anterior que minimizava o primeiro final coincide com a que minimiza o maior dos dois rácios piso/limiar. A 0,8×, **326 de 396** distribuições de lugares têm soluções que passam os dois tempos; a 1×, **zero**. A relaxação admite 1 698 vítimas observadas em T1, acesso antecipado ao T2 e 4 666 377 600 B de payload preparados antes do POST. O custo de preparar, conservar e entregar esses bytes ao staging e as releituras são concedidos gratuitamente. A escala aplica-se só ao READ cobrado. Os três SETs por geração conservam as suas durações na captura. [Seleções causais já testadas](../t1_local/README.md) · [Piso do primeiro conteúdo](../t1_set_floor/README.md)

## Que intervalo representa o decode?

No C269 pinado em `d0ebfbcc6c8f456bc1083027c1b08075a32824d8`, o servidor chama `llama_decode` em `tools/server/server-context.cpp:3617`. O ramo efetivamente observado é greedy, sem draft, com um pedido e EOG no fim. Após a primeira amostra e aceitação, `t_start_generation` recebe `ggml_time_us()`; na 47.ª, a diferença para a primeira amostra atualiza `t_token_generation` (linhas 3778–3799). A resposta copia o timing antes de libertar o slot (linhas 2149 e 3810–3816), com `predicted_n=47` e `predicted_ms` nas linhas 510–517. O servidor e o journal usam CLOCK_MONOTONIC. O SHA-256 de server-context.cpp é `657c331a707f0faf74615d19387088070c3dbd7559328619c9ef606a4ec8cc55`. [Validação dos settings e das amostras do target](../../../history_lookup/native_ids/verify.py) · [Implementação da auditoria](screen.py)

As chamadas 1 e 2 processaram 5 e 148 tokens. Entre a primeira amostra e a última ficaram comprovadas **46 chamadas unitárias**, da 3 à 48. Cada uma das 1 656 callbacks de decode está inteiramente dentro da respetiva chamada. De ENTER(3) a RETURN(48) passaram 9,990656346 s; o servidor reportou **9,993970 s** (4,702836 tok/s). Subtraindo a união das callbacks, 7,660238334 s, e concedendo mais 1 µs de quantização, permanecem **2,333730666 s** fora das callbacks no decode. Os dois relógios usam os seus próprios exteriores; no primeiro conteúdo são 6,008451991 s. A velocidade de 6 tok/s impõe 47/6 s de duração máxima no decode. A sensibilidade de 46 avaliações serve apenas ao orçamento de volume indicado no recibo. [Conversa física](../t1_local/README.md) · [Definição dos denominadores](../conversation/denominadores.md)

## Trabalho e conservação

| Região | Waves com serviço obrigatório | Gerações | Primeiras procuras | Lugares úteis na escolha conjunta a 0,8× | SET (worker-s) |
|---|---:|---:|---:|---:|---:|
| Somente primeiro final, antes do decode | 176 | 827 | 567 | 171 | 0,665081 |
| Decode dentro do primeiro final | 761 | 1 067 | 308 | 182 | 0,771196 |
| Decode adicional | 21 | 24 | 4 | 0 | 0,020176 |

De 2 354 reservas, 436 preloads têm custo zero. As 1 918 gerações próprias de procura pagam os três SETs. Dos READs, apenas os das 879 primeiras gerações podem ser cobrados; as outras 1 039 são releituras gratuitas. Nas 46 avaliações de decode, CPU/CUDA receberam 786/305 gerações e 10 390 291 200/4 031 856 000 B de SET. A escolha conjunta dispensa 1,815564 worker-s de primeiras leituras no decode antes da escala. Restam 1,238286 worker-s de primeiras leituras e 0,791371 worker-s de SET. O piso de parede de cada wave cobra o maior entre o trabalho serial mais longo e um quarto do trabalho total. Os resultados conservam tempos de worker e de parede separados.

As primeiras chaves são disjuntas entre as três regiões. Para cada distribuição dos 353 lugares as três DPs minimizam ambos os tempos em simultâneo, pois o custo de cada wave partilhada entra uma vez em cada relógio. A enumeração conserva a mesma atribuição ao calcular a margem de volume. O recibo dá hashes dos conjuntos concretos e os numeradores inteiros da conta. Os testes comparam a solução com enumeração de todos os conjuntos em problemas pequenos, incluindo um caso em que ótimos separados passam mas nenhum conjunto passa simultaneamente. [Solver de uma wave](../t1_set_floor/screen.py) · [Testes conjuntos](test_screen.py)

## Decisão de investimento e reprodução

**TRACE_DERIVED / FORMAL sob serviço fixo.** As travessias físicas do mesmo plano no NVMe, combinadas com SETs da captura e seleção ideal, dão pisos de primeiro conteúdo de 10,019168 e 9,993404 s. A melhor margem condicional aí é **6,596 ms**, para todos os custos ainda omitidos. Estas travessias só mediram E/S. A margem de 548,541 ms do cenário 0,8× diminui quando se usam estes preços físicos. Um próximo investimento exigiria seleção causal realizável e uma redução observada que suportasse cópias, dependências e coordenação dentro da margem. As duas seleções causais já testadas, recência e votos, falharam no mesmo T2. M3 permanece PARTIAL e M4 NOT_MET. A conversa de código, o uso sustentado e o produto completos exigem qualificação própria. [Duas travessias NVMe](../t1_set_floor/nvme.md)

R01/R02 usaram o protocolo de `f7698ac0` e código de `1cc0b674064d04e77fe1d9541aa4b9c734acff50`. As quatro entradas eram as duas preparações e os dois scores locais autenticados. A reprodução confirmou os grupos e o SHA da escolha original para o primeiro final. R01 demorou 1,10 s, RSS 75 680 KiB. R02 demorou 1,09 s, RSS 75 760 KiB. Ambos produziram os mesmos 18 557 B com SHA-256 `29d0539dd9248f494c9655850d9ce04e692ebbdf6092a0d8cc8c59206d4d3030`. A leitura do modelo limitou-se ao stat do inode. Não se executou inferência. O FAIL original de transporte entre processos permanece preservado. [Autenticação dos arquivos e inventário](../t1_local/README.md)

```sh
study=research/qualification-retake/phase_fd/integrated/t1_decode_gate
python3 -IB "$study/test_screen.py"
timeout 120s prlimit --as=536870912 --cpu=120 --fsize=1048576 -- \
  python3 -IB "$study/screen.py" --part "$PART40" --model "$MODEL" \
  --inventory "$INVENTORY" --prepared-dir "$NEW_SEALED_T1" --score-dir "$LOCAL_T2_SCORE" \
  --new-output-dir "$UNUSED_OUTPUT"
cmp "$UNUSED_OUTPUT/receipt.json" "$study/evidence/receipt.json"
```
