# Guardar os pesos que passaram pelo host em T1

**NO_GO no orçamento nominal de 47 saídas para este banco fixo.** Na entrada de T2, 314 das 353 chaves mais recentemente publicadas já estavam no primário. As 39 exteriores cobriam apenas 13 das 852 chaves distintas que faltavam ao primário e seriam necessárias até ao primeiro decode com reposição. Restam pelo menos **839 leituras**, ou **11 090 908 800 B**. Mesmo com capacidade ilimitada após a primeira falta, excedem em 400 602 186 B o orçamento de 10 690 306 614 B. A 4,5 GB/s essa diferença equivale a 89,023 ms na hipótese de banda do crivo. Na sensibilidade de 46 avaliações, o piso cabe com 349 397 816 B de margem. Ambas as políticas simuladas continuam a falhar os gates de prefill e decode dessa sensibilidade. [Protocolo congelado em 58bbe734](protocol.md) · [Recibo por fase e tier](receipt.json)

**Há um ganho incremental em contagem.** Ao expulsar primeiro os recuperáveis no banco, a origem por publicação exige menos 24 leituras até ao primeiro decode (−2,03%) e menos 81 no decode (−8,32%) face à captura das vítimas sob a mesma política. A restituição e os dados fixos de T2 estão incluídos. O decode fica 18,15% abaixo das 1 091 cargas R0 observadas e precisaria de eliminar mais 21 leituras para chegar às 872 do gate. A substituição sozinha também altera a agenda de serviço. A latência da conversa, as cópias e a interação com o pack permanecem **INCONCLUSIVE**.

| Agenda simulada | Disco até ao decode com reposição | Hits RAM até ao decode | Disco no decode | Hits RAM no decode |
|---|---:|---:|---:|---:|
| LRU sem banco | 1 373 | 0 | 1 333 | 0 |
| LRU, últimas vítimas | 1 234 | 139 | 1 143 | 190 |
| LRU, últimas publicações | 1 281 | 92 | 1 074 | 259 |
| Expulsão prioritária, últimas vítimas | 1 184 | 317 | 974 | 386 |
| Expulsão prioritária, últimas publicações | 1 160 | 301 | 893 | 524 |

As três primeiras comparações de controlo (sem banco, vítimas com LRU e vítimas com prioridade) reproduzem todas as contagens de origem por fase/tier e os bytes pedidos ao FD do crivo anterior. O R0 medido admitiu 1 263 gerações de prefill e 1 091 de decode. As linhas da tabela são **SIMULATED**. Protegem os experts de cada wave e mantêm 40 slots por camada, top-4, as duas chamadas 5+148, os cinco tiles e o estado de membros requerido na entrada do decode. A reposição concede permutações gratuitas, os relógios do consumidor e do pedido não foram modelados. [Agenda e comparação causal](../t1_primary_victim/README.md) · [Controlo de captura](../t1_bank_capture/README.md) · [Corte físico entre fases](../t1_manager_bank/decode_entry/README.md)

| Últimas publicações com expulsão prioritária | RAM CPU/CUDA | Disco CPU/CUDA |
|---|---:|---:|
| Call 5 | 2 / 0 | 38 / 11 |
| Call 148 | 160 / 59 | 602 / 348 |
| Reposição | 69 / 11 | 102 / 59 |
| Decode | 392 / 132 | 613 / 280 |

As 1 160 faltas através da reposição corresponderiam a 15 334 272 000 B úteis, 15 348 207 616 B pedidos no GGUF ou 15 337 390 080 B em janelas do pack. As 241 entregas da reposição incluem 161 de disco e 80 de RAM. O recibo inclui o mesmo detalhe para todas as alternativas.

### Preparação e validade dos bytes

O prefixo pré-POST selou as escolhas antes de abrir T2. Houve 2 181 ofertas completas (1 543 para destinos CPU e 638 para CUDA), 2 131 instalações e 50 promoções. A 353.ª identidade distinta surgiu na oitava chamada observada. No fim ficaram 260 chaves CPU e 93 CUDA, das quais apenas 33 e 6 estavam fora do primário. As vítimas davam 227 e 78 externas. Há 87 chaves comuns aos dois bancos.

| Bytes no sufixo T1 | Destino CPU | Destino CUDA |
|---|---:|---:|
| Retornos de pread no GGUF observados | 20 416 163 840 | 8 441 765 888 |
| Payload dos SET observados | 20 397 225 600 | 8 433 849 600 |
| Janelas de pack imputadas às mesmas ofertas | 20 401 373 184 | 8 435 564 544 |
| Payload lógico das instalações do banco | 19 881 676 800 | 8 288 438 400 |

As 50 promoções podem manter bytes antigos da mesma identidade imutável. Copiar em T1 todos os payloads para um staging distinto, antes de conhecer a decisão de publicação, moveria 28 831 075 200 B no host. Uma implementação que copiasse somente as 2 131 instalações moveria 28 170 115 200 B. Para eliminar essa cópia com o pack, o worker teria de ler diretamente para um registo provisório alinhado e transferir a sua propriedade ao banco. Até quatro registos em serviço acompanham os 353 retidos. Cada janela tem 13 221 888 B para 13 219 200 B úteis. As janelas e as etiquetas somam 4 720 263 168 B; restariam 497 360 896 B até ao stop se o restante consumo repetir o pico de controlo. Substituir os quatro stagings privados de 16 MiB só dará crédito de memória se saírem efetivamente da alocação e do pico.

O C291 no pin `c89c88b3` lê o pack antes dos três SET enquanto detém o claim. O staging atual pode ser sobrescrito pelo job seguinte. Cada provisório precisaria de permanecer exclusivo até ao último SET e à revalidação do vínculo sob o mutex. Uma falha, leitura que omita payload ou geração obsoleta descarta-o. Só uma publicação válida antes do selo instala ou promove. Em caso de duplicado, recicla-se o provisório depois da entrega e promove-se a cópia READY. A entrada fica imutável durante T2. O C269 do PFJ usava a mesma área privada para as componentes sucessivas. O journal confirma o serviço dos três payloads, enquanto a sua disponibilidade simultânea no host e a conservação da ordem de publicação com este C291 são hipóteses a validar. Os bytes transportados fisicamente pelo NVMe e a eliminação real do D2H continuam por medir. [Worker do pack](../../../packed_nvme_manifest/README.md)

O teste cobre o sufixo de T1 e um único T2 nominal. A experiência de produto mantém M3 PARTIAL e M4 NOT_MET. Reabrir o limite de volume exige outra seleção de entrada, medida capaz de mudar o orçamento, ou redução de trabalho numa fase contabilizada. O efeito favorável sobre o decode pode ser conservado numa combinação com essa nova premissa. O primeiro controlo teria de comparar as duas admissões na mesma agenda de publicação, verificar as três componentes por geração, medir aquisição em T1 e reposição, e medir o pedido completo.

### Reprodução

O primeiro comando de preparação lê apenas o prefixo pré-POST autenticado. As duas seleções privadas reproduziram o SHA-256 `27f03c1242123e82c9b8c77bd54a0c3479cd628e04451b45b3bfccc030656c15`. Os dois scores finais geraram SHA-256 `f2e1232d2466835931bdbe43420a61cb05fd0d473705c42ea5c5fbcabe87f049` em 0,57/0,61 s, com 74 772/74 104 KiB de RSS. Zero novos forwards, leituras de pesos ou GPU. O diagnóstico FAIL do PFJ integral permanece no arquivo. A parte privada 56 guarda os dois selos, os três scores e os três recibos da entrada no decode. O manifesto de 8 ficheiros e 129 989 B tem SHA-256 `566a385b4dee219e55843420cd737ec868405870d09d5bfa7efd88337147235d`.

```sh
unit=research/qualification-retake/phase_fd/integrated/t1_source_bank
python3 -IB "$unit/test_screen.py"
python3 -IB "$unit/screen.py" prepare --part "$PART40" --new-output-dir "$NEW_SEAL"
timeout 120s prlimit --as=536870912 --cpu=120 --fsize=1048576 -- \
  python3 -IB "$unit/screen.py" score --part "$PART40" --selection "$NEW_SEAL/selection.json" \
    --selection-sha256 27f03c1242123e82c9b8c77bd54a0c3479cd628e04451b45b3bfccc030656c15 \
    --new-output-dir "$NEW_SCORE"
cmp "$unit/receipt.json" "$NEW_SCORE/receipt.json"
```
