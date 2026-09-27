# Implementação documental 1.0.0

**GO documental; sem requalificação experimental.** A especificação aprovada permanece em `IMPLEMENTATION-SPEC.md` como registo da proposta. Este ficheiro descreve o resultado implementado e as suas diferenças de âmbito.

## Entrega

Uma classe baseada em article, macros comuns, schemas estritos, parser/verificador, derivação, gerador de campanha, compilação e publicação Linux no-replace. C2 é o piloto; C1 usa a mesma classe sem fork; R00 é um recorte do ledger; o dossier agrega versões congeladas. O sistema está isolado das dependências de inferência.

Os valores centrais vêm de JSON; quando a fonte selecionada é Markdown, há uma transcrição numérica explicitamente ancorada. A consistência do throughput C2 é verificada entre gate, resumo e razão de agregados. Latência D mantém arredondamento publicado. C1 usa tolerância documental compatível com números arredondados. Nenhum threshold experimental foi alterado.

A classe usa Latin Modern, já disponível. Não foram instaladas/distribuídas fontes tipográficas. Os gráficos são pgfplots com CSV derivado, vírgula decimal e espaço fino para milhares. C1/R00 usam tabelas em vez de figuras artificiais. As cores não são o único indicador de estado.

## Revisão e fronteira de evidência

O audit vincula o digest dos inputs e os bytes do PDF revisto. O build recusa um PDF diferente, inputs/derivados/audit alterados durante a execução, referências indefinidas, glyphs em falta ou overfull boxes. Dois diretórios limpos são usados para testar igualdade byte a byte; as dependências TeX/fontes são registadas por hash, sem copiar os ficheiros tipográficos.

C2 mantém CORRECTNESS_BLOCKED, metas falhadas, caps, referência longa interrompida, I/O físico desconhecido e ausência de controlo sustentado24 no mesmo protocolo. C1 mantém SUCCESS restrito, empate8/10, M2 parcial, CLI TIMEOUT e falha de referência. R00 não recupera admissões retiradas. O dossier não é nova revisão de literatura nem relato de todas as branches.

Foram incluídas apenas sete publicações compactas. Analysis-v2 integral, raw logs, prompts privados, amostras, linhas de logits e todos os manifests binários não fazem parte desta aquisição. Não se inferem igualdade de sampling, maior contexto exercitado ou tráfego físico de contadores lógicos.

## Reconstrução e integração

A execução anterior deixou registos de trabalho no histórico, mas os seus ficheiros intermédios não estavam no ambiente retomado. Fontes e código foram reconstruídos e os testes/builds repetidos. Os resultados desta entrega são os dos logs e manifests atuais, não contagens ou hashes copiados do histórico.

A clonagem direta estava bloqueada por resolução DNS neste sandbox. Isso não diagnostica o DNS do utilizador. O conector GitHub permitiu adquirir publicações e os objetos necessários. O commit main e as árvores raiz/docs foram reconstruídos com os mesmos Git object IDs. Os restantes subtrees são preservados por ID, não foram materializados/auditados. Isto é um object store bare seletivo, não um clone completo nem uma worktree qualificada.

Os commits locais são exportados em patches sobre a base real. Aplicação e CI num clone completo continuam por validar; não houve push/PR/merge nem edição da stack remota. Não foram executados modelos, benchmarks físicos ou downloads de pesos.

## CI e manutenção

A validação executada é documental e model-free; consultar o registo atual em `validation/`. Não se promove o status desse teste a CI global do Tesy. A ativação de CI documental remota pode ser uma integração separada depois da revisão local. Uma revisão científica externa também permanece por realizar.

A cópia da especificação em Markdown normaliza apenas whitespace no fim das linhas; o ficheiro original fornecido pelo utilizador não foi alterado. As sete publicações de evidência mantêm os seus bytes exatos.
