# Auditoria documental — D00-research-dossier

Revisão de autoria, não aprovação científica externa. Identidade e PDF revistos em audit.json.

| Claim | Fonte(s) | Afirmação / fronteira |
|---|---|---|
| CL-R00-NOVELTY | E-R00-STATUS | Novidade ampla não admitida no rastreio histórico. **Limite:** Não é nova revisão bibliográfica. |
| CL-R00-TRACER | E-R00-STATUS | Tracing diagnóstico no modelo real. **Limite:** Não é baseline de timing. |
| CL-R00-TOKENS | E-R00-STATUS | IDs iguais num teste emparelhado. **Limite:** Não demonstra logits bitwise. |
| CL-R00-LRU | E-R00-STATUS | Headroom derivado em count-space. **Limite:** Não é I/O físico. |
| CL-R00-BELADY | E-R00-STATUS | Oracle offline não causal. **Limite:** Não é política de produção. |
| CL-R00-PAYLOAD | E-R00-STATUS | Admissão de inventário inconclusiva. **Limite:** Provenance insuficiente não requalificada. |
| CL-R00-BYTES | E-R00-STATUS | Replay byte-weighted inconclusivo. **Limite:** Não promover simulação a tráfego físico. |
| CL-R00-STOCK | E-R00-STATUS | Baselines requerem rerun. **Limite:** Same-work não demonstrado. |
| CL-R00-FIT | E-R00-STATUS | Conflito estático no pin. **Limite:** OOM não é capacity bound geral. |
| CL-R00-CAPACITY | E-R00-STATUS | Admissões retiradas por host não provado. **Limite:** Nova campanha PHYSICAL requerida. |
| CL-R00-MMAP | E-R00-STATUS | Mmap span não equivale a bytes lógicos. **Limite:** NOT_COMPARABLE_MMAP_SPAN preservado. |
| CL-R00-LAZY | E-R00-STATUS | Expert tensors sem TENSOR_READ_LAZY. **Limite:** No-go local ao pin, não impossibilidade geral. |
| CL-R00-CROSSOVER | E-R00-STATUS | Base de execução não preservada. **Limite:** Conclusão requer rerun. |
| CL-R00-NEXT | E-R00-STATUS | Scheduler conjunto é pergunta aberta. **Limite:** Sem benefício/novidade já demonstrados. |
| CL-C1-STATE | E-C1-AUDIT | SUCCESS no âmbito original. **Limite:** Não transferir a cobertura C2. |
| CL-C1-IDENTITY | E-C1-AUDIT | Identidade física histórica publicada. **Limite:** Sem inspeção live. |
| CL-C1-CAPACITY | E-C1-AUDIT | Inventário e KV são grandezas com limites. **Limite:** Payload não é I/O físico nem toda a residência. |
| CL-C1-M4 | E-C1-AUDIT | 120B executado com paridade restrita. **Limite:** Não demonstra todos os prefixes. |
| CL-C1-M2 | E-C1-AUDIT | Accounting permaneceu parcial. **Limite:** read_bytes não é NVMe físico exclusivo. |
| CL-C1-M3 | E-C1-AUDIT | Melhoria no A/B curto emparelhado. **Limite:** Não prova taxa sustentada de 32 slots. |
| CL-C1-M5 | E-C1-AUDIT | Gate servidor passou, CLI TIMEOUT preservado. **Limite:** Wall time não é decode ininterrupto. |
| CL-C1-M6 | E-C1-AUDIT | Empate 8/10, maior custo target. **Limite:** Sem igualdade estatística ou superioridade geral. |
| CL-C1-FAULTS | E-C1-AUDIT | EIO abortou no surrogate. **Limite:** Não cobre todas as falhas/lifetimes. |
| CL-C1-PREFETCH | E-C1-AUDIT | Prefetch/speculation desligados. **Limite:** Não lhes atribuir os ganhos. |
| CL-C1-RAW | E-C1-AUDIT | Manifests/sínteses publicados; raws locais. **Limite:** Sem reanálise física neste PDF. |
| CL-C2-STATE | E-C2-SUMMARY | C2 fecha CORRECTNESS_BLOCKED. **Limite:** PASS de timing não certifica correção. |
| CL-C2-CORRECTNESS | E-C2-FINAL, E-C2-SUMMARY | Paridade independente GPU8/32 longa não validada. **Limite:** Surrogate e respostas funcionais não substituem o contrato target. |
| CL-C2-PERFORMANCE | E-C2-FINAL, E-C2-GATE | Gate C2-C passou no âmbito timing/recursos. **Limite:** Não atingiu 4 tok/s nem qualifica numéricos. |
| CL-C2-RESOURCE | E-C2-FINAL, E-C2-SUMMARY | Picos e limites têm âmbito e unidades diferentes. **Limite:** Não misturar cgroup, RSS e GPU nem inferir tráfego físico. |
| CL-C2-LATENCY | E-C2-LATENCY | Metas de first text e first final falharam. **Limite:** Ordem/caches impedem interpretação causal do comprimento. |
| CL-C2-UTILITY | E-C2-FINAL, E-C2-SUMMARY | Target 12/12 e stock 10/12 sob cap congelado. **Limite:** Dois exclusivos com stock sem final ao atingir o cap; sem superioridade geral. |
| CL-C2-OPERATION | E-C2-FINAL, E-C2-SUMMARY | Multiturn/cancel/shutdown publicados no âmbito limitado. **Limite:** Fronteira total 4096 e multi-client NOT_RUN. |
| CL-C2-IDENTITY | E-C2-FINAL, E-C2-SUMMARY | Modelo/backend/host são os da publicação histórica. **Limite:** Não houve inspeção live do target para este relatório. |
| CL-C2-FAILURES | E-C2-FINAL | Falhas e correções permanecem visíveis. **Limite:** Inventário das publicações selecionadas, não de todos os raws. |
| CL-C2-BOUNDARY | E-C2-FINAL | Não existe sustained24 novo no protocolo C2. **Limite:** Sem speedup causal sustentado 24/32. |
| CL-C2-NEXT | E-C2-FINAL | Próximo gate é referência independente admissível. **Limite:** Plano, não resultado executado. |
| CL-C2-AUTHORITY | E-C2-INDEX | Índice identifica o resumo inicial e a análise v2. **Limite:** Detalhe de eventos exige fonte integral v2 não incluída aqui. |
| CL-C2-RAW | E-C2-FINAL | Publicações compactas versionadas, raws ficaram locais. **Limite:** Sem reprodução experimental neste pacote. |

## Revisão aplicada

C2: CORRECTNESS_BLOCKED preservado; PASS de timing separado de correção; cgroup peak não é RSS; 7000 MiB não são 7 GiB; picos de runs diferentes identificados; latência SSE não renomeada percentis por token; sem causalidade sustentado24/32. A vantagem funcional mantém suite/cap/custo e não se generaliza.

C1: commit original, números arredondados tratados como publicados; SUCCESS restrito, empate8/10, M2 parcial, CLI TIMEOUT e referência bloqueada mantidos. Não se transferiu validação C2.

R00 e dossier: recorte histórico do ledger e versões específicas dos relatórios; não inventário exaustivo de todas as branches nem pesquisa de literatura nova. Dados retirados não foram requalificados.

Correções visuais: rótulo longo R00 com quebra apropriada; separação após tabelas; formatos numéricos pt-PT. O gate de overfull não foi relaxado. Todas as páginas foram revistas após estas correções.

As âncoras/seletores completos estão em evidence-spec.json; o índice não substitui a leitura das fontes. Experiências e raws não foram repetidos. Revisão externa: NOT_RUN.
