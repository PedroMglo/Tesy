# O C292 preserva as fronteiras numéricas ao observar o router seguinte

**PASS de exatidão para esta sonda e este corpus.** Dois processos carregaram a mesma DSO C291 e o GPT-OSS-120B original do NVMe. No perfil com a sonda ativa, 1 803 das 2 130 gerações ausentes nos destinos L1–35 receberam um ID previsto antes de o manager consultar a chave. O ensaio mediu a disponibilidade da informação. O número de prefetches lançados foi zero; a antecedência necessária para acabar de ler, copiar e publicar cada expert requer outra análise. [Previsão congelada](protocol.md) · [Resultados e relógios em ns](result.json)

| Workload e destino | Sites positivos | Linhas previstas | READY identificados a tempo / procurados | LOADING identificados a tempo / procurados | Ausentes identificados a tempo / procurados | E32 até à última E33, soma |
|---|---:|---:|---:|---:|---:|---:|
| Prefill CPU | 144 | 4 536 | 3 259 / 3 674 | 954 / 1 194 | 700 / 795 | 1 297,794 ms |
| Prefill CUDA | 61 | 1 891 | 1 197 / 1 367 | 369 / 466 | 288 / 331 | 485,018 ms |
| Decode CPU | 768 | 768 | 1 885 / 2 343 | 0 / 0 | 588 / 729 | 374,365 ms |
| Decode CUDA | 352 | 352 | 991 / 1 133 | 0 / 0 | 227 / 275 | 230,659 ms |

O PFJ fechou 33 chamadas, com 189 entradas em cinco tiles de 32 e uma de 29, e 32 passos unitários. Nos destinos CUDA, a fonte L24 executou na CPU em seis tiles de prefill e 32 passos de decode. No ON, o auditor contou 7 547 previsões. Em cada braço verificou 7 768 quartetos autoritativos, contando L0. Ao juntar as 3 303 previsões dos cortes C270 arquivados, obteve o digest calibrado. OFF e ON reproduziram os mesmos 12 755 pedidos na ordem selada, com os IDs, slots e gerações da parte 95. Quatro workers por processo encerraram. [Auditoria das entregas](join.py) · [Controlo da DSO](../README.md)

Os dois braços reproduziram os **3 266 ficheiros, 88 704 231 B**, da C270 e da C292 original, incluindo cinco vetores finitos de 201 088 logits, 1 500 payloads centrais C127 e o witness de 996 comparações de componentes em 166 combinações. O contexto foi 8192. A identidade de todos os bytes do KV interno continua sem teste direto neste cliente. A neutralidade numérica abrange estes cortes com o cliente de captura e o seu callback original. [Referência C127/C270](../../../../packed_nvme_manifest/capture_numeric/grade.py) · [Verificação independente dos brutos](review.py)

**Custo observado.** O produtor usou cinco GET por site; releu gammas, matriz e bias da camada seguinte em cada site. Em 4 636 GET, leu 1 430 363 904 B do buffer CUDA_Host, legível pela CPU, em 42,587 ms acumulados. As outras 1 989 GET moveram 641 898 496 B lógicos do CUDA0 em 77,378 ms. ASK→DATA inclui computação do produtor e sincronização do scheduler. Da entrada E32 à última E33 decorreram 1 782,812 ms no prefill e 605,024 ms no decode pelo relógio do thread que submetia o grafo. Estes intervalos incluem as GET, preparação do operando, projeções, seleção e publicação dos ranks. As medianas E33→lookup ausente foram 211,209 e 220,259 ms no prefill, 9,421 e 9,312 ms no decode, respetivamente nos destinos CPU e CUDA. Vários experts partilham a mesma janela. A disponibilidade da previsão precede a sua utilização; a duração de serviço por job e a disputa por largura de banda continuam por cobrar.

| Braço | Processo | PFJ | Raw final | Pico cgroup | Pico GPU | CPU / GPU / NVMe |
|---|---:|---:|---:|---:|---:|---:|
| OFF | 33,092 s | 72 672 registos | 96 008 697 B | 18 020 618 240 B | 6 878 MiB | 71,75 / 51,95 / 43,85 °C |
| ON | 34,285 s | 102 678 registos | 98 904 814 B | 18 227 216 384 B | 6 882 MiB | 72,38 / 51,95 / 46,85 °C |

A família ocupou 213,877 s, incluindo C118 de 61 amostras em cada braço e a validação numérica. Swap zero, ambos os scopes inativos após fecho. A C55 prévia durou 60,018 s; o cap máximo canónico foi 21 743 271 936 B. A medição usou a árvore limpa `f97b9dd59d966764255426e334e06f45930fe964`. Um par em ordem fixa com cliente de captura não qualifica um efeito de produto nem mede o custo de observação no servidor C281 de callback nulo. O ganho útil e as formas naturais de largura 5 e 20 permanecem em aberto.

A repetição inicial de PREPARED_ONLY em `73e4e2d7` ficou preservada com zero cargas. O revisor final acrescentou a pertença das procuras à sua wave e a das entregas à tile; a preparação foi repetida em destino novo antes dos dois forwards. O comando de replay exige as âncoras públicas e as pastas privadas seladas.

```sh
python3 -IB "$NUMERIC/review.py" --family "$FAMILY" \
  --family-sha256 e762554f1ab0372a9534da0ec857aaccf3fc82ddf4f586f2e84dca1df3a65156 \
  --build-dir "$DSO" --original-family "$C292_PART54" --r0-dir "$C270_PART23" \
  --new-output-dir "$NEW"
```
