# Seleção do runtime antes do primeiro forward

**MEDIDO.** O cliente C270 e o servidor C281 carregaram a libllama privada escolhida. Ambos os controlos negativos carregaram de propósito a biblioteca original. Tanto a comparação da lista de bibliotecas numéricas com as VMAs como o verificador de origem por dispositivo/inode recusaram essa seleção. As seis invocações terminaram em 2,259 s, com pico de cgroup de 144 621 568 B, teto de 512 MiB e swap zero. O número de modelos carregados, pedidos e forwards foi zero. [Protocolo](protocol.md) · [Recibo dos seis processos](startup-r01.json)

| Executável | Seleção | Bibliotecas numéricas mapeadas | Objetos inicializados pelo loader | Resultado |
|---|---|---:|---:|---|
| C270 | Relink de controlo | 5 | 18 | ELF bit a bit igual ao original |
| C270 | Candidato | 5 | 18 | ELF privado esperado |
| C270 | Original onde se exigia candidato | 5 | 18 | Identidade recusada |
| C281 | Relink de controlo | 7 | 24 | ELF bit a bit igual ao original |
| C281 | Candidato | 7 | 24 | ELF privado esperado |
| C281 | Original onde se exigia candidato | 7 | 24 | Identidade recusada |

A sonda suspendeu cada processo na leitura de um FIFO privado para observar o executável, os descritores e as VMAs. O cliente C270 terminou com código 1 ao receber um ficheiro de IDs vazio. O C281 terminou com código 0 após fechar o FIFO de gramática e imprimir a ajuda. Em cada caso o diário do loader pertence ao PID observado. Os auxiliares de driver usados durante inferência exigem verificação no processo físico.

A C55 seguinte observou 61 amostras em 60,017 s, com um mínimo de 24 475 787 264 B de memória disponível e teto admissível de 22 280 142 848 B. Essa janela admitiu os recursos de E20 na estação. Cada lançamento exige ainda o seu próprio C118 antes de abrir o modelo.

Para reproduzir a compactação desde o arquivo privado, indicar as duas raízes originais ou as cópias verificadas e um nome de saída novo. Os caminhos temporários registados pelo loader são comparados como texto.

```sh
python3 -B research/qualification-retake/phase_fd/integrated/profile/compact_startup.py \
  --smoke-dir "$SMOKE" --window "$C55" --new-output "$NEW"
cmp "$NEW" research/qualification-retake/phase_fd/integrated/profile/startup-r01.json
```

## Dois processos numéricos C270

**PASS para observar o serviço no próximo par de conversas.** Os dois processos carregaram o candidato com SHA-256 `911b3be5b529d8e07409c12cf600ca9f7f6182f7a397fc6de265e5ea4be254eb`. Cada um verificou os 1500 payloads selecionados e cinco vetores completos de logits finitos da C127. O verificador de consumo examinou 996 componentes em 166 combinações. A entrada foi o prefill de 189 IDs fornecidos, em seis tiles de 32+32+32+32+32+29, seguido dos mesmos 32 IDs, um por chamada. O processo OFF encerrou sem journal. O ON encerrou após os quatro joins e deixou um journal selado de 7 879 264 B e 82 075 registos. A verificação offline repetiu o gate numérico contra o raw C127 e a conservação no journal. Para a identidade do FD usou o par dispositivo/inode recolhido no arranque pelo monitor. [Compacto C270](c270-r01.json)

| Observador | Duração C118 | Idade da C118 no arranque | Cliente | Pico do cgroup | Pico GPU | Raw |
|---|---:|---:|---:|---:|---:|---:|
| OFF | 60,184 s | 44,675 ms | 35,164 s | 15 856 644 096 B | 6882 MiB | 89 041 814 B |
| ON | 60,175 s | 43,001 ms | 35,341 s | 15 851 438 080 B | 6882 MiB | 96 920 892 B |

Os dois arranques usaram E20, sem swap nem motivo de stop. A família durou 205,229 s incluindo as duas janelas C118 e validação. Há uma observação por braço. A diferença de 0,177 s entre os tempos de cliente deixa por medir a neutralidade temporal do observador.

| Origem das leituras, ON | Gerações carregadas | Bytes devolvidos pelo pread | Payload das cópias |
|---|---:|---:|---:|
| Prefill de 189 | 3441 | 45 529 227 264 | 45 487 267 200 |
| 32 decodes | 1060 | 14 025 490 432 | 14 012 352 000 |

As 4501 reservas tiveram publicação. Cada uma exigiu três READ e três SET, com 13 503 de cada. Os pedidos e os retornos de pread totalizaram 59 554 717 696 B. A soma da duração dos READ pelos workers foi 83,525 s, e a união no relógio desses intervalos foi 27,124 s. Para SET, as duas durações foram 5,213 s e 5,051 s. A soma e a união incluem sobreposições diferentes. Determinar o custo no caminho crítico do T2 requer a sua própria trajetória, com as fronteiras de 5 e 148 observadas. Os contadores de pread descrevem o contrato do kernel. O tráfego físico que chegou ao dispositivo permanece desconhecido.

Para repetir a verificação usar o analisador do commit de medição `1d3109c19a831cd0c485cc0ac0ab72da1e0d7688`, a captura integral C127 e a árvore privada C270 terminal. O comando lê e autentica os dois braços e produz um ficheiro público novo.

```sh
OPENBLAS_NUM_THREADS=1 python3 -B research/qualification-retake/phase_fd/integrated/profile/compact_c270.py \
  --family-dir "$FAMILY" \
  --family-sha256 9aa14a7cd43197f24f53f3d6169c21a030de34cf83569c09777dd387076984c1 \
  --c127-reference "$C127" --analyser "$MEASUREMENT_ANALYSE" --new-output "$NEW"
cmp "$NEW" research/qualification-retake/phase_fd/integrated/profile/c270-r01.json
```
