# Tesy — primeira reunião de orientação (versão revista, 17-10-2026)

**Duração:** ~11–12 min de exposição + ~3–4 min de discussão. **Objetivo:** explicar o problema, três ganhos de engenharia interna e a pergunta de tese, sem expor o detalhe da arquitetura/campanhas.

## Materiais
- `APRESENTACAO.md`: estrutura dos 10 slides e respetivos claims/limites.
- `GUIAO.md`: versão breve e respostas prováveis.
- [GUIAO_ORAL_COMPLETO.md](GUIAO_ORAL_COMPLETO.md): **texto integral para dizer durante os 10 slides V3**, 12 min 10 s de fala planeada, com notas e perguntas. PDF e DOCX guardados na Library da reunião.
- `GLOSSARIO.md`: termos técnicos, conceitos científicos e siglas, com explicações curtas.
- `RESULTADOS_SELECIONADOS.md`: dados, métodos, limites e origens dos gráficos.
- `REFERENCIAS.md`: bibliografia curta, links primários e fronteiras de comparação.
- `RESUMO_ACADEMICO.md`: versão de uma página, adequada para partilhar com a orientadora.
- `PERGUNTAS_DIFICIES.md`: perguntas e respostas privadas, para preparar a discussão.
- `data/resultados_apresentacao.csv`: dados numéricos selecionados.
- `assets/`: figuras reutilizáveis. As figuras antigas não substituem a versão atualizada das métricas documentadas.

A apresentação PowerPoint **V3** (10 slides com notas) corrigiu o slide 3 para mostrar explicitamente computação CPU ou GPU sem implicar que todos os experts executam na GPU. Existem ainda versão em PDF para apresentar, resumo académico de uma página e folha de apoio privada em PDF. Os ficheiros binários e `build_presentation.js` são arquivados na **Library pessoal**, em `/Tesy/Tese/Primeira-Reuniao-2026-10-17/`, e entregues na conversa. **Os binários não estão nesta branch do GitHub**; a narrativa, o guião, o glossário e os dados de origem estão versionados aqui. Guardar o artefacto efetivamente apresentado e a identidade da documentação.

## Mensagem central
O Tesy investiga execução local e serviço dos experts de LLMs MoE muito maiores que a VRAM, preservando a seleção original dos experts. Já há medições favoráveis a **modificações do caminho de execução**: wave-skip C104, layout lossless C293 e reuso entre tiles C274. Estas não são prova de superioridade global do Tesy sobre alternativas bem configuradas.

## Separação essencial
**Não apresentar o aumento de slots 32→40→44 como melhoria arquitetural isolada.** É essencialmente uma troca entre capacidade residente e desempenho; o efeito pode ainda combinar geometria de waves. Slots44 pode surgir apenas como contexto de orçamento de memória.

Os *gates* de promoção e os objetivos M3/M4 foram regras internas de engenharia; serão objeto de revisão e negociação científica, nunca falsificados ou retroativamente alterados. Resultados abaixo dos gates continuam evidência com âmbito e limitações.

## Evidência de origem
Consulta da branch publicada `campaign/120b-exact-expert-service-20261006T194311Z` em `623a5b97b6e14a39bc671f6d81e7a993a3efe7cb`, relatórios C100/C104/C129/C142/C274/C282/C293/C320. Sem nova inferência nem validação física nesta preparação.

Estado: `BROAD_NOVELTY_NO_GO / ENGINEERING_AND_MEASUREMENT_GO`; M3 PARTIAL; M4 NOT_MET; perfil operacional `slots40-persistent` opt-in. **Material de conversa inicial, não artigo científico nem documentação integral do Tesy.**
