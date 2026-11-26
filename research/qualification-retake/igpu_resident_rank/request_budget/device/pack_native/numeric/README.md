# Paridade do observador do pack no C292

**MEDIDO e REPRODUZIDO.** As três capturas do 120B no NVMe interno produziram a mesma árvore de 3 266 ficheiros e 88 704 231 B que o C127, o C270 independente e o C291 histórico com pack. O digest por nome, tamanho e conteúdo é `3b1c13734120f430d779960e3e8123eb58ffeee1947a1844636743b1e3aa1f03`. Os três relatórios numéricos têm o SHA-256 `9bd460d4ff291de7e4821b4fe010e88c1832d0ab4098ee483a124b581166e686`. A decisão é **GO para observar o C281** nas bibliotecas C291 de produção identificadas no build R02. [Protocolo](protocol.md) · [Revisão integral](evidence/physical.json)

Cada processo verificou 1 500 payloads de seis fronteiras em 250 estados, duas máscaras, 996 checks em 166 combinações e cinco vetores F32 completos e finitos de 201 088 logits, incluindo o fim do prefill e os passos 0, 1, 7 e 31. As 189 posições e os 32 tokens de continuação foram fornecidos. A configuração conservou contexto 8192, ub32, 40 slots e quatro workers. O launcher do serviço continua no respetivo controlo operacional.

| C291 com pack | Journal do observador | Segundos no cliente C292 | Pico do cgroup (B) | FD do pack observado | Pico GPU (MiB) |
| --- | --- | ---: | ---: | ---: | ---: |
| Controlo recompilado | OFF | 32,703 | 16 341 258 240 | 4 amostras independentes | 6 878 |
| Candidato | OFF | 32,298 | 18 539 794 432 | 118 amostras | 6 878 |
| Mesmo candidato | ON | 31,377 | 16 456 695 808 | 114 amostras | 6 878 |

Os três cgroups usaram zero swap. A seleção de 18 fornecedores no arranque e os 21 inicializadores totais foram verificados no PID e no journal do loader de cada processo. A C55 recolheu 61 amostras e mediu um mínimo de 25 537 130 496 B disponíveis. Cada lançamento teve a sua C118. Os tempos medem uma execução com captura de tensores e leitura de testemunhos de bytes. Uma amostra fixa por braço não estima o custo do observador num servidor de conversa.

O journal ativo tem 72 850 registos, 33 entradas/retornos e 38 tiles. As 4 501 reservas terminaram em 4 501 leituras de pack e publicações, 13 503 SET e 4 saídas de workers. Houve 1 715 promoções e 1 715 entradas descartadas da fila depois da promoção. Os syscalls devolveram 59 511 717 888 B e os SET copiaram 59 499 619 200 B. O revisor registou zero retry, cancelamento, erro, perda e trabalho pendente terminal. O PFJ ficou ativo desde a posição zero. A ativação com histórico e trabalho potencialmente em curso na entrada do segundo pedido tem de ser observada na própria conversa.

O controlo original usou a DSO histórica `04af70ea…0819` na parte 54. O novo controlo `77274012…6b25` e o candidato `9cfa8807…a0c5` partilham a ferramenta de compilação e 164 dos 166 objetos. Na atual estação 19 secções ELF alocáveis do controlo recompilado diferiram da versão histórica. A requalificação numérica liga expressamente ambas as versões. O digest externo do build é `cfd616fda7fcdac7aaf6774f9b6d2aac7ea5186a5629fa33eb1bff58a00b34c8`. [Política de build R02](../dso/current-toolchain.md)

**Proveniência.** Protocolo congelado em `9c3bcd71`, R01 em `dd35618a4cb3ae8e026a8f8ee75709ebf90bcf82` e R02 em `8c7a70dbe5324398e503302f45f05460740eae73`. R01 conserva FAIL_PRESERVED no revisor após o exit 0 do controlo. Quatro amostras independentes de /proc ligam o mesmo FD O_DIRECT da mesma captura ao seu PID e às VMAs. A reabertura verificou as duas referências numéricas e executou apenas os dois overlays. O recibo terminal R02 tem SHA-256 `c94bd52fbfe937cd3b3cddb5addf16c0a2a8950e2580dbf010632d4819ac4d76`; o revisor independente reproduziu o compacto `adf10943d43bdf7c1a0703f2248e238bbaa972f7ee2d3c75689bbe080e114325` sem modelo. O arquivo da parte 94 conserva o controlo. A parte 95 conserva 6 596 ficheiros e 185 397 503 B da preparação, execução e revisão R02, verificados depois da publicação. [Falha e reabertura](reopen.md) · [Manifesto da parte 95](../../../../../private_archive/part-95.json)

Reprodução offline com os diretórios privados originais ou as cópias do arquivo. O revisor verifica cada árvore, monitor, início, ambiente, loader, FD, journal e grade, e exige um destino novo.

```sh
python3 -IB "$NUMERIC/review.py" --family "$FAMILY_R02" --family-sha256 "$FAMILY_SHA" \
  --failed-family "$FAMILY_R01" --control-fds "$LIVE_FD_R01" --build-dir "$DSO_R02" \
  --r0-dir "$C270" --preflight-dir "$STATIC" --original-family "$C292_PART54" \
  --new-output-dir "$AUDIT_NEW"
```
