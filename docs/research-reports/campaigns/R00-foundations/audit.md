# Auditoria documental — R00-foundations

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

## Revisão aplicada

C2: CORRECTNESS_BLOCKED preservado; PASS de timing separado de correção; cgroup peak não é RSS; 7000 MiB não são 7 GiB; picos de runs diferentes identificados; latência SSE não renomeada percentis por token; sem causalidade sustentado24/32. A vantagem funcional mantém suite/cap/custo e não se generaliza.

C1: commit original, números arredondados tratados como publicados; SUCCESS restrito, empate8/10, M2 parcial, CLI TIMEOUT e referência bloqueada mantidos. Não se transferiu validação C2.

R00 e dossier: recorte histórico do ledger e versões específicas dos relatórios; não inventário exaustivo de todas as branches nem pesquisa de literatura nova. Dados retirados não foram requalificados.

Correções visuais: rótulo longo R00 com quebra apropriada; separação após tabelas; formatos numéricos pt-PT. O gate de overfull não foi relaxado. Todas as páginas foram revistas após estas correções.

As âncoras/seletores completos estão em evidence-spec.json; o índice não substitui a leitura das fontes. Experiências e raws não foram repetidos. Revisão externa: NOT_RUN.
