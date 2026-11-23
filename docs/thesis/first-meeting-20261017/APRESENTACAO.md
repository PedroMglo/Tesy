# Apresentação revista — 10 slides / 15 minutos

A versão PowerPoint contém notas do apresentador. O guião alinhado está em `GUIAO.md`; termos explicados em `GLOSSARIO.md`.

| Slide | Mensagem técnica principal | Evidência | Tempo |
|---|---|---|---|
| 1. Tesy | Tema e envelope de hardware | GPT-OSS120B; 8GiB VRAM, 32GiB RAM, NVMe | 0:40 |
| 2. Problema | Capacidade ≠ custo de movimentação ≠ latência útil | MoE e prefill/decode | 1:00 |
| 3. Mecanismo | O router e os pesos são autoridades, residency é decisão de execução | Arquitetura conceptual | 1:10 |
| 4. Waves | Evitar trabalho redundante, com o mesmo executável | C104 OFF/ON −75,35% frio; −27,72% warm | 1:55 |
| 5. Layout lossless | Melhor entrega com os mesmos bytes e routing | C293: −7,47% nominal, −6,05% código no custo integrado | 1:25 |
| 6. Reuso entre tiles | Ganho local **e** regressão posterior | C274: −18,19% prefill; −8,91% first-final código; C282 decode nominal regressão | 1:35 |
| 7. Inferência honesta | Ganho interno ≠ superioridade face a runtime externo | Baselines fortes ainda necessários; slots não são inovação | 1:00 |
| 8. Hipóteses delimitadas | Negativos explicam o espaço de desenho | C235/C258/C318/C319/C320 | 0:50 |
| 9. Bibliografia | Prior art direto | Shazeer; Switch; HOBBIT; fMoE | 0:40 |
| 10. Pergunta de tese | Validação científica e âmbito | Proposta; discussão | 1:10 + 3–4 min |

## Notas de interpretação dos gráficos

**Slide 4 (waves):** OFF normalizado a 100% de duração; ON = 24,65% no frio e 72,28% no warm. O gráfico visualiza **duração remanescente**, não percentagem de throughput nem segundos. C104 mesmo binário, dois pares. C100, contraste entre builds, revelou regressão de decode — não esconder.

**Slide 5 (layout):** valores são reduções medianas emparelhadas **de custo total integrado em trabalho fornecido**; nominal7,472543% e código6,048126%. Os 33 logits completos foram bitwise idênticos ao gold R0 selecionado. Não usar o ganho do microbenchmark isolado como se fosse ganho de produto.

**Slide 6 (reuso):** prefill−18,189548% em teacher-forced C271 e first-final−8,914968% em código livre C273 têm populações diferentes. C282 encontrou decode nominal−10,70339% na comparação R0→E. Esta versão não é perfil geral e altera geometria de atenção/router; nem toda a melhoria é atribuível só a eliminar recargas.

## Linhas vermelhas

- Não voltar a apresentar 40→44 slots como otimização arquitetural — é maior consumo de memória e possível mudança de wave geometry.
- Não somar percentagens de fases, nem misturar tempos de prefill com custos totais ou bytes lógicos com tráfego físico.
- Não dizer que passou M4, que os protótipos têm qualidade geral, ou que o Tesy é mais rápido que runtimes de referência.
- Os thresholds dos *gates* eram internos. Podem ser revistos **prospetivamente** com a orientadora, mantendo resultados/FAILs originais.
- Não expor code patches, full model manifests, raw traces ou detalhes de políticas experimentais nesta primeira reunião.

## Fontes do próprio repositório
`research/C104-WAVE-TOGGLE-RESULT-20260928.md`; `research/C100-SERVER-WAVE-CONFIRM-RESULT-20260928.md`; `research/C274-BLOCKS-EXPERT-REUSE-CLOSURE-20261004.md`; `research/C282-R2-CAUSAL-QUALIFICATION-CLOSURE-20261005.md`; `research/C293-INTEGRATED-EXPERT-STORE-COST-NO-GO-20261006.md`; `research/C320-EXACT-EXPERT-SERVICE-ARCHITECTURAL-CLOSURE-20261007.md`.
