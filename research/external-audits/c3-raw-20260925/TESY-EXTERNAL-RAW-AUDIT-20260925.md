# Tesy — auditoria externa dos raw publicados

Data: 2026-09-25. Âmbito: bundle recebido na conversa; nenhuma alteração ao repositório,
nenhuma execução de modelo, GPU ou nova campanha física. O código Tesy de auditoria não foi
usado para decidir os resultados: a recomputação foi implementada separadamente.

## Decisão

**Integridade confirmada; valores stock reproduzidos no âmbito documentado; FAIL de logits
Tesy reproduzido. A atribuição causal da diferença continua por resolver.**

As duas classes de inconsistência que os testes adversariais da revisão anterior demonstraram
que o auditor podia deixar passar **não aparecem nestes dados**: os SSE coincidem com as
respostas/sumários e não existem lacunas de processo no interior dos traces. Não há motivo,
a partir desta auditoria, para repetir os vinte runs stock.

Esta não é uma certificação da execução física original. É uma auditoria independente dos
bytes publicados, da sua coerência e dos cálculos que podem ser repetidos a partir deles.
Não transforma os resultados stock em speedup Tesy e não flexibiliza a gate numérica falhada.

## 1. Identidade e integridade

- Arquivo: `tesy-vertical-raw-evidence-20260924.tar.gz`.
- Bytes: **1646346**.
- SHA-256 calculado: `83b88fe09da4b1e038aec810537c7a30d702a7811dc78d4ebc29189f184a7bf6`.
- SHA-256 de `bundle-manifest.json`: `57d9b9a1271eefc6ee8c705a7f767858646000f02219db485662485f94ec53a7`.
- Source head do empacotamento: `48c7f5ec27f80c34fa13b955c1bf8d23faea6f48`.
- **211/211 entradas** com tamanho e SHA-256 correspondentes ao manifesto.
- 212 ficheiros no arquivo incluindo o manifesto; 4030817 bytes descomprimidos.
- Nenhuma entrada duplicada, caminho absoluto/traversal, symlink ou entrada extra não declarada.
- 128 ficheiros JSON e 3 171 registos JSONL foram analisados com rejeição de chaves duplicadas
  e de literais JSON não finitos.
- As 21 notas de redacção correspondem às 21 cópias `doctor-public.json`.

Isto identifica os bytes auditados. Não permite reconstruir os pesos, executáveis ou
ficheiros originais omitidos a partir dos seus hashes.

## 2. Stock: reconstrução dos vinte runs

Fonte: `results/full-stock-chat-eval-valid-20260924T222803Z/`.

Para cada uma das vinte combinações repetição/tarefa/colocação:

1. Comparei a sequência de frames de `stream.sse` com `sse-events.jsonl`.
2. Reconstruí o texto visível concatenando `delta.content`.
3. Verifiquei unicidade de request ID, ordem temporal dos eventos, terminação `[DONE]`, ausência
   de erro SSE e consistência de finish reason, usage e timings.
4. Comparei a reconstrução com `run.json` e com o resumo publicado.
5. Recalculei cada registo derivado de recursos, os vinte registos por run e os quatro agregados.
6. Cruzei argv previsto/observado, paths/digests do executável e CUDA, identidade do modelo e
   contas do estimador de capacidade. Estas são verificações de coerência dos registos publicados.

**Resultado:** vinte runs coerentes; os vinte registos e os quatro agregados publicados
foram reproduzidos sem diferenças. Existem vinte PIDs e vinte request IDs distintos; os traces
de monitorização não se sobrepõem segundo os respectivos relógios monotónicos.

| Tarefa | Colocação | TTFT mediana / p95 (s) | Pedido mediana / p95 (s) | Backend média por token: mediana / p95 entre runs (ms) |
|---|---|---:|---:|---:|
| Extracção | ngl0 | 2,514247 / 2,559060 | 6,211659 / 6,284475 | 62,555059 / 63,569676 |
| Extracção | ngl12 | 1,615283 / 1,644374 | 3,738127 / 3,754399 | 36,189309 / 36,277868 |
| Código | ngl0 | 2,360814 / 2,418222 | 9,402138 / 9,694503 | 59,721874 / 61,828472 |
| Código | ngl12 | 1,474141 / 1,480381 | 5,443817 / 5,627067 | 33,666575 / 35,214181 |

Por tarefa/colocação há apenas cinco runs. O p95 nearest-rank é portanto o máximo das cinco
observações, não uma caracterização robusta da cauda. `predicted_per_token_ms` não é a
distribuição das latências de cada token: a aritmética persistida é `predicted_ms/(predicted_n-1)`.

A redução da mediana do pedido de ngl0 para ngl12 é **39,8208% na extracção** e **42,1002% no
código**, exclusivamente para estas colocações stock e estes workloads. A calibração 0/8/12
que escolheu ngl12 não está no bundle, pelo que a sua selecção prospectiva não foi re-auditada.

### Endpoints dos tempos

O primeiro conteúdo visível foi identificado directamente nos eventos. `run.json.ttft_s`
é registado entre **0,078097 e 0,347042 ms** depois desse primeiro arrival. O fim do pedido é
registado entre **0,086934 e 0,166604 ms** depois do arrival de `[DONE]`.

Não são timestamps bitwise idênticos; mantive os dois endpoints separados. Não alterei os
valores originais nem inventei um threshold novo para os fazer passar. O bundle não contém
todos os timestamps independentes necessários para recomputar, por exemplo, launch-to-health:
para esse campo foi verificada a agregação dos escalares persistidos, não o relógio original.

O tempo do pedido excede a soma `prompt_ms + predicted_ms` do backend entre aproximadamente
5,860 e 8,000 ms. Isto é apenas uma consistência dos valores registados, não uma medição
separada de cada custo de transporte/cliente.

### Conteúdo, tokens e qualidade

Todos os runs de extracção reconstruíram o mesmo texto, 69 tokens reportados, finish `stop`.
Todos os runs de código reconstruíram o mesmo texto, 128 tokens reportados, finish `length`.
Não existem chunks não vazios de `reasoning_content` no grupo publicado.

Há 59 chunks visíveis por resposta de extracção e 119 por resposta de código: **um chunk SSE
não equivale a um token**. Os IDs exactos amostrados não foram capturados; não foram inferidos
por retokenização. Estes registos não permitem medir uma distribuição TPOT token-a-token.
O texto de código termina em `# Exemplos`, sem exemplos completos. Os outputs e budgets não
constituem uma avaliação formal de qualidade ou conclusão de tarefas.

## 3. Telemetria e proveniência

### Grupo stock

- 1 273 amostras GPU, todas `status=OK`, com números finitos.
- 1 251 amostras completas de processo; todas `VmSwap_bytes=0`.
- 22 objectos `process={}`, apenas no final dos traces; nenhuma lacuna intermédia.
- Nenhum registo parcial que contivesse swap positivo foi descartado.
- Dois runs têm duas amostras finais vazias; os restantes têm uma.
- Máximo RSS: **12 925 100 032 bytes**.
- Máximo GPU usado: **6 020 923 392 bytes**.
- Mínimo MemAvailable: **23 389 261 824 bytes**.
- Mínimo GPU livre calculado dos registos: **2 564 816 896 bytes**.
- Máximos observados: **57 °C / 37,76 W**.
- Intervalos de amostragem observados aproximadamente 121–186 ms.

As ausências finais são compatíveis com terminação; o arquivo não tem um evento de liveness
associado a cada amostra vazia que prove a causa. A conclusão é **zero swap observado nas
amostras completas**, não prova de ausência contínua de swap entre observações.
Existe swap ocupado global do host, cerca de 57,5 MB nos snapshots. Isso não é swap do processo.

### Root do blocker

38 amostras GPU válidas; 36 completas de processo, sem swap; duas vazias apenas no final.
RSS máximo 13 125 591 040 bytes; GPU máximo 975 175 680 bytes; MemAvailable mínimo
23 557 824 512 bytes; GPU livre mínimo 7 610 564 608 bytes; máximos 51 °C / 30,48 W.
Não encontrei violação dos headrooms amostrados.

### Limites da proveniência

Os vinte registos stock usam o mesmo digest de executável e de CUDA, com argv previsto igual
a observado. O blocker tem identidades distintas e coerentes com o seu build manifest.
Os snapshots públicos reportam o host físico esperado, modelo/driver identificados e nenhum
processo GPU concorrente no momento do probe. Isto não reexecuta os probes nem verifica os
bytes dos binários/modelo que não foram distribuídos.

O probe `cuda_toolkit` está `NOT_AVAILABLE` nos 21 doctors. Isso **não** significa que o backend
CUDA não estava mapeado; apenas não estabelece a versão do compilador via aquele probe.

A redacção remove **o resultado completo de `snapshot.storage_topology.lsblk`**. O `findmnt`
restante reporta o caminho do modelo em btrfs sobre `/dev/nvme0n1p3[/home]`. Não recupera
informação do campo omitido. Não é necessário publicar mountpoints privados para esta análise.

## 4. FAIL de logits Tesy: recomputado

Fonte: `results/vertical-live-diagnostic-20260924T215315Z`.

Measurement commit: `6f9beefc6b346b2a30d5e4a4af05c28f934d9289`.
Measurement tree: `ae518f02ea30ca61e5113aeb194bd512b58a9821`.

Dois vectores de 201 088 F32 little-endian, 804 352 bytes cada; ambos inteiramente finitos.
Cálculos de erro realizados em float64.

| Métrica | Recomputação |
|---|---:|
| max absolute error | 0,155649185180664 |
| max absolute reference | 18,18376922607422 |
| relative max | 0,008559786656194 |
| cosine | 0,99997661362415 |
| limiar relativo congelado | 0,005 |
| limiar cosine congelado | 0,9999 |
| orçamento absoluto equivalente | 0,09091884613037 |
| razão erro relativo / limiar | 1,711957331 |

**A gate de relative max falha e a de cosine passa. O resultado global continua FAIL.**
O erro não se limita a um único outlier: 478 coordenadas excedem o orçamento absoluto global
correspondente ao limiar relativo. 201 087 das 201 088 coordenadas não são numericamente iguais;
essa contagem, sozinha, não mede gravidade nem qualidade.

O maior erro está no índice 191634, de -4,490162372589111 para -4,645811557769775.
O argmax de ambos é o índice **94852**, com segundo colocado **109941**.

### Porque greedy igual não salva este teste

Margem stock entre primeiro e segundo: **2,760650634765625**.
Erro absoluto máximo: **0,15564918518066406**.
Logo `2 × erro máximo = 0,3112983703613281`, menor que a margem.

Para estes dois vectores, uma perturbação limitada por esse erro máximo não consegue trocar
o vencedor: para qualquer concorrente, a diferença pode diminuir no máximo `2*erro`.
Portanto o argmax preservado é compatível e previsível pelo bound, mesmo com FAIL numérico.
Isto não prova igualdade de distribuições ou comportamento de tokens posteriores.

### O que continua sem atribuição independente

O stderr reporta FFN bitwise stock nas layers 0/1, h=1 e erro FFN 4,12584316e-05 na layer 2,
comparação de bytes host/GGUF e shadow CPU bitwise stock. Estes são registos do diagnóstico.
O bundle não contém os vectores FFN intermédios, saídas por expert, activations do suffix ou
rotas posteriores. Não pude recomputar a causa, distinguir associação das somas de diferenças
de kernels, nem provar que a alteração FFN sozinha produz a alteração final.

Mantém-se a ordem ao Codex para a atribuição causal. Não há fundamento aqui para alterar a
residência, afrouxar tolerâncias ou declarar o backend GPU inadequado.

## 5. Capacidade

Recalculei as nove relações bytes/bandwidth dos três cenários NVMe. Estão aritmeticamente
correctas, com GB/s decimal e tamanhos de 1/4/16 GiB explicitados pelos bytes.

Não são bandwidth medida, bytes por token ou previsão de tok/s. O relatório continua a
classificar materialização física de pesos e suporte >RAM como desconhecidos/não validados.
As medições C1 de RSS e de alocação GPU por layer citadas no relatório não têm raw separado
neste pacote. Os candidatos maiores não têm artefactos exactos nem execução publicada aqui.

## 6. Estado a comunicar à equipa

```text
BUNDLE_INTEGRITY: PASS_RECOMPUTED
STOCK_OUTPUTS_AND_PUBLISHED_AGGREGATES: PASS_RECOMPUTED_WITH_SCOPE_LIMITS
SSE_VS_SUMMARY_CONSISTENCY: PASS
INTERIOR_PROCESS_TELEMETRY_GAPS: NONE_OBSERVED
TESY_LOGIT_CRITERION_FAILURE: REPRODUCED
NUMERICAL_CAUSE: NOT_ESTABLISHED_BY_THIS_BUNDLE
TESY_PERFORMANCE: NOT_RUN
OVER_RAM_LOADER: UNKNOWN
```

A auditoria do conteúdo acessível pode ser encerrada neste âmbito, com referência ao digest.
Uma flag genérica `pending_external_audit` não deve apagar as limitações: a publicação pode
registar separadamente o que foi recomputado, o que ficou apenas declarado e o que não existe.
Não alterei essa flag no Git.

Não é necessário interromper o Codex, repetir os vinte runs stock ou pedir outros modelos
por causa desta revisão. O novo facto prioritário para ele é que o FAIL foi confirmado a partir
dos vectores originais e que preservar argmax não o torna uma falsa falha do validador.

## 7. Reprodutibilidade desta auditoria

`audit_bundle.py` lê o tar sem executar ficheiros nele incluídos, verifica a integridade,
reconstrói os resultados e escreve JSON no-replace. Depende apenas da biblioteca padrão Python
e NumPy. Não necessita de repo, modelo, GPU ou internet.

`test_audit_bundle.py`: 12 fault probes locais passaram, incluindo SSE vazio, output adulterado,
arrival invertido, lacuna intermédia, processo parcial com swap, NaN e chave JSON duplicada.
A primeira execução deste harness de testes tinha uma fixture chamada `run` que colidia com
`unittest.TestCase.run`; foi renomeada para `record`. O erro inicial foi preservado. Isto não
alterou os raw, as fórmulas de auditoria ou qualquer campanha Tesy.

A versão de Python/NumPy e ambiente da recomputação está em `execution-environment.json`.

Limite final: **auditoria de evidência publicada não é uma nova medição de performance no
portátil nem prova integral de origem de bytes/bibliotecas não distribuídos.**
