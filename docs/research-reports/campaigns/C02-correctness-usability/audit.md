# Auditoria documental — C02-correctness-usability

Revisão de autoria, não aprovação científica externa. Identidade e PDF revistos em audit.json.

| Claim | Fonte(s) | Afirmação / fronteira |
|---|---|---|
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
