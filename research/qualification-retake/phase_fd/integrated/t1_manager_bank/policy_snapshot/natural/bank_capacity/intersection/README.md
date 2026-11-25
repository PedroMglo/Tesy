# O efeito de ampliar o banco das últimas publicações

**NO_GO para atingir o volume nominal D=47 apenas com mais entradas nesta ordem.** No histórico da parte 40, 5 das 33 entradas que K386 acrescenta a K353 evitam uma primeira leitura obrigatória. Seriam necessárias 31. K390 cru, o maior ponto admitido pelo pico histórico deste processo, acrescenta 6 úteis em 37. A inclusão dos sufixos garante que qualquer K entre 353 e 390 tem pelo menos 833 leituras obrigatórias, face às 808 admissíveis. O contributo de capacidade é positivo e fica quantificado para combinações que mudem outra parcela do pedido. [Protocolo](protocol.md) · [Recibo](receipt.json)

| Banco | Entradas adicionais | Dessas, já no primário | Dessas, ausentes e dispensáveis | Dessas, úteis CPU / CUDA | Piso CPU / CUDA | Piso total | Payload obrigatório | Melhoria do piso a 4,5 GB/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| K353 | 0 | 0 | 0 | 0 / 0 | 545 / 294 | 839 | 11 090 908 800 B | controlo |
| K386 | 33 | 15 | 13 | 5 / 0 | 540 / 294 | 834 | 11 024 812 800 B | 14,688 ms |
| K390 | 37 | 16 | 15 | 6 / 0 | 539 / 294 | 833 | 11 011 593 600 B | 17,626 ms |

**TRACE_DERIVED.** O selo de T1 contém 2 181 publicações completas de 1 787 chaves distintas. As listas já tinham sido preenchidas à 353.ª, 386.ª e 390.ª ofertas, respetivamente. A segunda requisição entra com 1 440 membros no primário. O prefill solicita 1 751 chaves distintas e 852 dessas estão ausentes, 558 CPU e 294 CUDA. A reposição dos membros R0 do primeiro decode acrescenta zero chaves distintas a estas 852. As releituras durante a reposição continuam possíveis com os 40 slots reais. Entre as 353 publicações de controlo, apenas 13 contêm chaves obrigatórias ausentes do primário, todas de CPU. Em K386 são 18 e em K390 são 19. Os três conjuntos continuam a exigir as mesmas 294 chaves CUDA.

**FORMAL, sob as hipóteses do corte.** Cada chave ausente do primário e do banco paga pelo menos um payload de 13 219 200 B. Mesmo permitindo retenção ilimitada depois da primeira leitura, permutas grátis, cópias grátis e codec grátis, o piso K386 excede em 334 506 186 B o orçamento D=47. Em K390 o excesso é 321 286 986 B. Faltariam, respetivamente, 74,335 ou 71,397 ms de folga noutra parcela, mantendo os restantes custos e a taxa assumida de 4,5 GB/s. Na relaxação D=46 o piso já cabia em K353, com folga de 349 397 816 B. Em K386 e K390 a folga sobe para 415 493 816 B e 428 713 016 B. **INCONCLUSIVE** nesse ramo e para a latência real do pedido. Os bytes alinhados imputados ao pack estão separados no recibo. O efeito de cache nas releituras, os transportes RAM/CUDA, a sobreposição e o custo de manter/descomprimir o banco não foram medidos.

O cenário de compressão da amostra sustenta a pergunta sobre K386. O mesmo K também cabe em formato cru no pico histórico da parte 40. K390 cru usa o orçamento específico deste processo. O número adicional de chaves com utilidade seria igual se qualquer representação exata armazenasse as mesmas listas. As **vítimas expulsas** têm outra ordem e este fecho não se transfere para essa política, para outros pedidos ou para outro estado de entrada. [Picos, representação e garantia de fallback](../README.md) · [Ordens de publicação e de expulsão](../../../../../t1_source_bank/README.md)

Pré-registo `cd13fad8`. Checkout limpa `829a2174a7abb2e3f48a54ae94ccd230d5dfe73d`, árvore `6b34f8cda73f997a4a8e4b109c925df2b0353c7b`. Duas invocações independentes de seal, 0,15 e 0,14 s, e de score, 0,51 e 0,52 s. Pico até 75 688 KiB. As seleções privadas coincidiram byte a byte com SHA-256 `a33d8311bd702bad30c7118b923a318f73ae573722258bb23fd88ba39295e51f`. Os dois recibos coincidiram com `78cb569ded48d8e5509a2703cd9ec3fb3cccd6f5b090bd5cf0e667ad0a815548`. O FAIL da campanha de captura original conserva-se. Zero leituras de pesos, novos pedidos ou execuções GPU.

```sh
unit=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/bank_capacity/intersection
run() { timeout 60s prlimit --as=536870912 --cpu=60 --fsize=524288 -- python3 -IB "$unit/screen.py" "$@"; }
run seal --part "$PART40" --new-output-dir "$NEW_SEAL"
sha256sum "$NEW_SEAL/selection.json"
run score --part "$PART40" --selection "$NEW_SEAL/selection.json" \
  --selection-sha256 a33d8311bd702bad30c7118b923a318f73ae573722258bb23fd88ba39295e51f \
  --new-output-dir "$NEW_SCORE"
cmp "$unit/receipt.json" "$NEW_SCORE/receipt.json"
```
