# Auditoria documental — C01-scale-lab

Revisão de autoria, não aprovação científica externa. Identidade e PDF revistos em audit.json.

| Claim | Fonte(s) | Afirmação / fronteira |
|---|---|---|
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

## Revisão aplicada

C2: CORRECTNESS_BLOCKED preservado; PASS de timing separado de correção; cgroup peak não é RSS; 7000 MiB não são 7 GiB; picos de runs diferentes identificados; latência SSE não renomeada percentis por token; sem causalidade sustentado24/32. A vantagem funcional mantém suite/cap/custo e não se generaliza.

C1: commit original, números arredondados tratados como publicados; SUCCESS restrito, empate8/10, M2 parcial, CLI TIMEOUT e referência bloqueada mantidos. Não se transferiu validação C2.

R00 e dossier: recorte histórico do ledger e versões específicas dos relatórios; não inventário exaustivo de todas as branches nem pesquisa de literatura nova. Dados retirados não foram requalificados.

Correções visuais: rótulo longo R00 com quebra apropriada; separação após tabelas; formatos numéricos pt-PT. O gate de overfull não foi relaxado. Todas as páginas foram revistas após estas correções.

As âncoras/seletores completos estão em evidence-spec.json; o índice não substitui a leitura das fontes. Experiências e raws não foram repetidos. Revisão externa: NOT_RUN.
