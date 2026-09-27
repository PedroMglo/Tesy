# Tesy research reports

Sistema documental model-free: uma classe LuaLaTeX, fontes congeladas, seletores explícitos, testes adversariais e publicação local no-replace. Não altera o runtime de inferência, protocolos, thresholds ou resultados originais.

## Documentos e âmbito

| ID | Conteúdo |
|---|---|
| `C02-correctness-usability` | Campanha 2 no snapshot `81531d9dc33caddbbf07928106de47cfe2a6d42a`. Mantém `CORRECTNESS_BLOCKED`. |
| `C03-boundary-prefill` | Edição revista v1.0.0 de C3 em `a0b673965b6e7c5aac69ae464d8275c176f4b14a`; seis fontes congeladas, auditoria e PDF de seis páginas. |
| `C01-scale-lab` | Auditoria original em `c67529e290844bb3d9033615072d5878014a46bc`. `SUCCESS` apenas no âmbito histórico. |
| `R00-foundations` | Recorte do ledger datado de 24 setembro, em main `7a7d3dcbd1ff8e594ac57459c3db06306083c3ca`. Não é retrospectiva exaustiva de todas as branches. |
| `D00-research-dossier` | Síntese R00/C1/C2, com versões e digests dos relatórios filhos congelados. |

O dossier D00 é a entrada histórica para R00/C1/C2; os relatórios de campanha contêm contrato, resultados, falhas e limites. O corte de D00 é 26 setembro 2026. **C3 tem edição própria**: consultar C03, [CURRENT-LAB.md](CURRENT-LAB.md) e a publicação autoritativa em `research/C3-FINAL-20260927.md`. D00 não foi retroativamente reescrito. Autoria pessoal/universidade/orientação não foram inventadas: `author` é null.

O contrato de cobertura e a divisão de responsabilidades estão em [REPORTING-PROCESS.md](REPORTING-PROCESS.md). A CI deteta campanhas fechadas sem relatório revisto; C2 e C3 passam esse gate na revisão atual. PDFs gerados ficam fora de Git e são distribuídos como artefactos versionados separados.

## Executar

Requer Python 3.11+, o package fixado em `tools/requirements.txt` e, apenas para PDF, LuaLaTeX, latexmk, biber, Latin Modern e os packages da classe. Não há instalação ou download automático. Dependências documentais não pertencem ao package de inferência. `validation/environment.json` regista o ambiente usado.

A partir desta pasta:

```bash
python -m unittest discover -s tests -v
python tools/verify_evidence.py C02-correctness-usability

# Só depois de uma alteração intencional e revista:
python tools/derive_report_data.py C02-correctness-usability
python tools/build_report.py C02-correctness-usability --mode draft

# Depois de rever os claims e todas as páginas do draft:
python tools/build_report.py C02-correctness-usability --mode release --check-reproducible
```

`verify_evidence.py` deteta derivados desatualizados; não os corrige. `derive_report_data.py` é a operação explícita de regeneração. A derivação substitui cada ficheiro atomicamente, mas não promete uma transação de toda a pasta: um conjunto interrompido/misto é recusado pelo verificador.

Release exige `audit.json` com o digest exato dos inputs **e SHA-256 do PDF efetivamente revisto**. Um PDF diferente é recusado, mesmo que os ficheiros de texto coincidam. A revisão desta entrega é revisão de autoria, não peer review externo nem aprovação científica de um orientador. `scientific_endorsement` permanece false.

As releases ficam em `published/<id>/v<versão>/release/`; drafts usam `draft-<digest>`. Uma versão publicada não é substituída: mudar conteúdo exige nova versão. A publicação usa `renameat2(RENAME_NOREPLACE)` em Linux; se indisponível, falha sem fallback sujeito a races. `_build/` conserva diagnósticos locais. Ambas as pastas estão fora de Git.

## Fontes e autoridade

`sources/catalog.json` associa cada fonte a commit, path, Git blob SHA, SHA-256 e tamanho. `sources/objects/` contém cópias exatas de sete publicações compactas, não pesos ou dados brutos. As cópias não são uma nova fonte autoritativa: tornam o mesmo snapshot verificável offline sem incorporar a história separada do laboratório em main.

A associação commit/path foi adquirida pelo conector GitHub. Tamanho, Git blob SHA e SHA-256 foram verificados sobre os bytes. Esses hashes não provam, sozinhos, a validade de uma experiência. Verificar o resumo JSON também não recalcula os pesos nem todos os manifests que ele menciona.

Num clone completo com os objetos já disponíveis:

```bash
python tools/verify_evidence.py C02-correctness-usability \
  --source-mode git --repo /caminho/Tesy --sources-only
```

O modo Git não faz fetch, não muda branch e não usa HEAD como fallback. Recusa configurações partial/promisor para evitar aquisição implícita. Para derivar e compilar nesse modo, usar a mesma opção nesses comandos: o modo faz parte do lock. O modo default desta entrega é `snapshot`.

Cada família de afirmações declara as suas fontes. C2 usa o gate para desempenho, resumo para estado e agregados, fecho para âmbito/falhas, índice para autoridade e relatório D para latência. O índice aponta analysis-v2 para detalhe de eventos; o ficheiro integral e os raws não foram reanalisados neste pacote. C1 usa a auditoria no commit original. R00 é deliberadamente um recorte do ledger.

## Dados e estados

`campaign.json` é metadata editorial. `evidence-spec.json` declara seletores JSON Pointer, âncoras textuais, unidades, operações, crosschecks, classes e limites. `evidence-lock.json` regista a resolução. `generated/` contém valores, macros, CSV e índice gerados; não editar à mão.

Só há operações `sum`, `ratio` e conversões unitárias enumeradas; não há `eval` de expressões dos dados. Duplicados, extras, seletores ausentes, booleans como números, não finitos, ciclos, aliases de fonte/path, symlinks e unidades incompatíveis são recusados. Valores arredondados de Markdown mantêm a precisão publicada; não se inventam raws de maior precisão.

Classe de evidência, estado científico, disponibilidade dos dados e estado editorial são dimensões distintas. Uma campanha FAIL/BLOCKED pode ter um relatório correto. `PASS` documental nunca muda `CORRECTNESS_BLOCKED` para PASS científico. Claims históricos/retirados usam `\historicalclaim`, não `\claim` atual.

## Nova campanha e correções

```bash
python tools/new_campaign.py CXX-nome-real \
  --base-commit <SHA-completo-da-base-real> --date YYYY-MM-DD
```

O nome tem de ser novo. O gerador cria `DRAFT`/`NOT_RUN`, sem métricas inventadas. Registar explicitamente a entrada em `registry.json`; a separação evita uma atualização global parcial silenciosa. Não se assume que C3 ainda não existe. Congelar pergunta/contrato antes da experiência, depois acrescentar apenas fontes adquiridas e verificadas.

A ordem das doze secções é comum: síntese, pergunta, contexto, contrato, metodologia, resultados, falhas, interpretação, limitações, decisão, próximo gate e apêndices. Figuras são opcionais. A edição entregue é pt-PT; `language` muda hifenização e formatos, não traduz automaticamente a narrativa e todos os rótulos.

Uma alteração material exige novo `CHANGELOG`, versão, derivados, lock e audit. Não corrigir o ficheiro histórico para coincidir com o PDF. O dossier também fixa as versões e digests dos filhos; não aponta implicitamente para “o último”.

## Limites e segurança

Quatro garantias são separadas: integridade documental; regeração dos derivados; build/PDF; reprodução experimental. Nesta entrega a última permanece `NOT_RUN`, e raws `NOT_ACCESSED`. Igualdade de PDFs só é afirmada após dois builds limpos no ambiente registado, não para qualquer plataforma.

Specs e LaTeX são código de autoria confiável a rever. `-no-shell-escape`, paths verificados e cópias isoladas **não são uma sandbox contra LuaTeX hostil**. A validação não prova toda a semântica da prosa nem infere a unidade verdadeira de um número. Revisão humana continua necessária.

O workflow documental em `.github/workflows/research-reports.yml` executa os testes model-free, a verificação de todos os relatórios registados e compila previews PDF byte-reprodutíveis. Cada run conserva um artifact `tesy-reports-preview-…` durante 14 dias; é material de revisão, não uma publicação científica. O build TeX fica separado das dependências do runtime.

As releases são automáticas para os relatórios inscritos em `release-automation.json`. Em cada PR documental, `.github/workflows/publish-research-report.yml` recompila em modo `release` no ambiente da CI e exige que o PDF seja byte-a-byte igual ao hash visualmente revisto em `audit.json`; este é o preflight, ainda sem publicar. Depois do merge em C3, o mesmo workflow recompila, cria a tag imutável `reports-<report-id>-v<version>` e a GitHub Release com PDF, `release.json`, `evidence-lock.json` e `SHA256SUMS`. Não há passo de UI nem tag manual. Uma Release existente nunca é alterada: se os seus inputs ou PDF diferirem, a CI falha com `RELEASE_VERSION_ALREADY_PUBLISHED`; aumentar `campaign.json.version`, regenerar derivados e refazer a auditoria é obrigatório. Alterações sem efeito no relatório (por exemplo, este README) comparam a mesma identidade publicada e não criam outra Release. Falhas por toolchain, auditoria, hash, tag pré-existente ou Release prévia não publicam nada. Isto não depende de `main`, que não é a base autoritativa do Scale Lab. As releases são o local citável para PDFs oficiais; os PDFs e diretórios de build continuam fora de Git.

Os registos em `validation/` e `IMPLEMENTATION.md` descrevem a entrega original, antes da integração; o estado atual é descrito em `CURRENT-LAB.md` e no PR. Testes globais do Tesy e execução experimental: NOT_RUN nesta integração.

Nos estados apoiados por texto, o teste automatizado é lexical: verifica o rótulo na âncora, não interpreta negações ou toda a semântica. Escolher âncoras positivas estreitas e verificar o contexto na revisão; preferir campos JSON explícitos quando disponíveis.
