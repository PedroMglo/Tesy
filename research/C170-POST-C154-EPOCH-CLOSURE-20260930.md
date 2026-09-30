# C170 — fecho da época após C154

## Decisão

**POLICY_NO_GO_TESTED_SCOPE.** A instrumentação e o replay de decode passaram no âmbito do probe. Nenhuma melhoria física nova foi confirmada nesta época. A política CPU52/GPU44 foi rejeitada antes de implementação.

O mmap fica **INCONCLUSIVE_TOOLING_OR_MEASUREMENT**: a referência independente não completou a cobertura. Isto não é um NO_GO de performance do upstream. O fecho resulta dos gates dos dois ramos, sem esgotar o orçamento.

## Instrumentação, replay e política

C156 verificou a geração byte a byte, os macros C/C++, bibliotecas e limites do snapshot/journal. As suites dirigidas, fixtures nativas e o percurso de lançamento foram exercitados. Não foi executada a suite integral do repositório.

C159 passou o bridge contra o original C140 e a comparação logger OFF/ON: 1500 estados, 250 comparações e cinco logits completos bitwise. C161 conserva o FAIL original do leitor. C162 reparou a interpretação de `pool_used` como IDs de slots e de `next_wave` como ondas do grafo fixo, incluindo ondas vazias. A reanálise, sem repetir o modelo, passou 1728 witnesses e 57 logits completos.

C163 completou dois pares OFF/ON no mesmo binário. As medianas do overhead foram 0,0935693% em warm prefill e 0,0900890% em decode. Isto autoriza o uso delimitado dos spans; não prova invariância universal do scheduling nem promove timing instrumentado a desempenho de produção.

O replay gerou autonomamente hits, misses, reservas, victims, filas, gerações, hotness e recência. Reproduziu os estados finais nos três casos, cada um com 6768 demands de decode. A ordem externa dos workers entra como condição observada. O replay não copia os victims do journal. Prefill/waves e o bridge para o estado warm do servidor continuam NOT_RUN.

CPU52/GPU44 foi escolhida no development e congelada antes da avaliação dos holdouts. O crédito temporal condicionado foi:

| Caso | Crédito condicionado de decode |
|---|---:|
| Development | 9,233% |
| SQL, holdout | 7,147426% |
| Energy, holdout | 7,108855% |

O gate exigia pelo menos 8% nos dois holdouts. Falhou. Não houve retuning, implementação, quotas ou confirmação física. A alternativa custaria mais 2 643 840 000 B de expert copies CPU, com GPU inalterada.

Estes cenários usam os serviços observados e o estado real slots44, acrescentando slots vazios. Não são um oracle certificado, um upper bound da classe inteira ou ganhos implementados. Não rejeitam toda a residência estática/adaptativa.

## Diagnóstico mmap e falhas preservadas

C166 passou o smoke FILE_PAGING e três processos nativos: NONE, STATE e VERIFY. Os cinco logits completos coincidiram bitwise. STATE/VERIFY coincidiram em 1080 payloads selecionados; passaram 10128 verificações de componentes, incluindo biases.

Sem observer, prefill32 demorou 57,278986 s. Os quatro forwards seguintes demoraram 6,384727 / 2,813887 / 3,043614 / 3,598593 s. O máximo observado de `read_bytes` do processo foi 61 151 330 304 B.

No braço VERIFY, prefill32 demorou 54,357709 s, dos quais 3,117187 s foram medidos dentro da verificação canónica. Foram verificados logicamente 22 372 346 880 B. Bytes verificados não são tráfego NVMe. Verificação e captura estão dentro dos callbacks, que estão dentro do forward: não se somam estes spans.

O custo nativo já é elevado sem observer neste caso curto. A verificação não explica sozinha essa latência. As diferenças entre modos têm cache/ordem como alternativas; não são uma comparação causal de speedup. O caso 32+4 também não identifica a causa exclusiva do timeout histórico 189+32.

C167 falhou na primeira referência: a FFN coincidiu, mas o readout posterior de routing estava incorreto. C168 reproduziu sem modelo o lifetime do allocator: intermediários não marcados como outputs podem ser reutilizados. A proteção com `ggml_set_output` corrigiu a evidência. O binário e FAIL antigos permanecem.

C169, nova tentativa causal, passou 120 rows das camadas 0–23. Na camada 24, IDs e pesos de routing passaram nos cinco pontos; a FFN não coincidiu bitwise, com erro absoluto máximo 0,00048828125 e valores finitos. A execução parou; camadas 25–35 ficaram NOT_RUN.

O trace observa `ffn_moe_out` em buffer CUDA0 já na camada 24, com activation/router/outputs de experts em CUDA_Host nessa camada. A referência isolada dessa camada instanciava apenas CPU. Não está demonstrado o mesmo mapa de operações/fusão da execução nativa completa. Proveniência de buffer não basta para identificar toda a aritmética. A causa exclusiva do mismatch continua UNKNOWN. Não se alteraram tolerâncias nem se atribuiu corrupção ao modelo.

## Identidade e âmbito

Modelo: `582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d`, stat intacto; nenhum download ou requantização.

- C75 original: `27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5`, preservado.
- Logger qualificado: `0fd9de9cf08a0ee6f6fdaad0328efa221ada5c7b`.
- Upstream: `8019dc563b1ecbae6b161a70c3a1359f1b206c1e`, com o loader patch existente, hash `bc57a67d571c83ccf3c4a4268b5cb0d6bc071ea3daf78c6f4ac99ad9bb3333bb`.

Protocolos e receipts identificam measurement SHAs, fontes, binários e bibliotecas efetivamente mapeadas. `measurement-heads.json` reúne os HEADs, sem hashes circulares.

O probe 2044+153+47 forwards não é o servidor C142 com 47 output IDs e 46 avaliações de decode. Native32+4 não qualifica 189+32, sessão, warm153 ou posições até 8192. Experts CPU não implica toda a FFN CPU.

O census inicial observou aproximadamente 2,024 GB residentes e 74 process maps ilegíveis. A ownership de page cache é desconhecida; equal-memory fica INCONCLUSIVE. FILE_PAGING manteve reclaim permitido, swap zero e guards de host/dispositivos. Não houve limpeza global de cache ou ação sobre processos alheios.

## Perfil útil, M3 e M4

Slots40 conserva o opt-in C143 e os resultados históricos: quality12/12, holdout8/8, sessão19/20 e retrieval7936/85, nos respetivos âmbitos. A integração do launcher C143 com pesos continua NOT_RUN.

Slots44 conserva C140 numérico e C142 nominal153 confirmado. Não herda quality, sessão ou 7936 de slots40. M3 permanece parcial; M4 não foi atingido. Nenhum default ou serviço mudou.

## Accounting, integridade e publicação

O checkpoint de preparação está em `budget-checkpoint.json`: cerca de 38 min 50 s live de 4 h; cerca de 3 h 37 min wall de 8 h naquele checkpoint; 963 217 576 B de raw charge de 4 GiB. A reserva de 900 s está incluída. O charge inclui conservadoramente o root model-free C156/build.

Os 39 processos de modelo somam 1058,426 s de uptime dentro dos envelopes. Isto não mede apenas tempo ativo ou compute. Build, análise e espera do owner não foram cronometrados separadamente: UNKNOWN. Não se inventa uma causa dominante para o elapsed wall. FAILs, inventários e cleanup estão contados; os envelopes não são somados novamente às suas fases.

Sete manifests foram revalidados por SHA/tamanho. Todos os processos/scopes próprios terminaram; GPU com 12 MiB ocupados. Os novos ficheiros Git não contêm ELF, builds ou raw físico. Os FAILs históricos permanecem.

Branch: `campaign/120b-post-c154-residency-20260930T094754Z`. Resultado anterior ao commit de fecho: `f1df6d4`; HEADs completos no checkpoint. Remoto mantém `8f7a07e1db2e526b9f9de30abb86bdda602483f3`; main mantém `7a7d3dcbd1ff8e594ac57459c3db06306083c3ca`. Commits locais; sem push, PR, merge ou ativação. O saldo de uma época fechada não autoriza outra época automaticamente. O accounting final em `final-budget.json` regista live 2329.599013 s, wall 13338.047106 s, saldos respetivos 12070.400987 / 15461.952894 s e raw 963217576 B. A janela de análise/fecho após a verificação live é registada separadamente, com charge física zero.

## Próximo discriminante e reprodução

Primeiro, provar o mapa de nós/backends/fusão da FFN na fronteira 24 e nas camadas GPU; construir a referência canónica correspondente. Numeric e retained prefix precedem qualquer screen de performance. Não repetir cegamente 189+32 com timeout maior. Uma nova política de residência exige hipótese material e holdouts independentes.

Para reanalisar os holdouts sem alterar originais, criar diretório novo em `/tmp` e copiar apenas o `protocol.json` de C164 para ele:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/residency_holdout_replay_analyze.py /tmp/<diretorio-novo-com-protocolo>
```

O protocolo aponta aos raw locais por caminho/hash. Outputs são no-replace. O teste do allocator está em `tools/reference_output_lifetime_test.cpp`, com comandos de build em C168. O gate de referência é `mmap_phase_gate.py reference <stdout> <layer>`; não se aceita um status preliminar isolado.

Fontes primárias pinadas, também auditadas localmente: [grafo MoE](https://github.com/ggml-org/llama.cpp/blob/8019dc563b1ecbae6b161a70c3a1359f1b206c1e/src/llama-graph.cpp#L2340), [scheduler](https://github.com/ggml-org/llama.cpp/blob/8019dc563b1ecbae6b161a70c3a1359f1b206c1e/ggml/src/ggml-backend.cpp#L1124), [allocator](https://github.com/ggml-org/llama.cpp/blob/8019dc563b1ecbae6b161a70c3a1359f1b206c1e/ggml/src/ggml-alloc.c#L693). Nenhum claim de novidade.
