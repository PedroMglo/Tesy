# O controlo R0 voltou a reproduzir C127 com o driver atual

**MEDIDO e REPRODUZIDO em 26 de novembro.** O cliente C270 com a biblioteca C269 de R0 reproduziu o digest da árvore completa da captura C127 independente. O avaliador confirmou os 1 500 payloads internos, os cinco vetores completos de logits e as 166 combinações com 996 componentes de testemunho. O modelo era o GPT-OSS-120B MXFP4 original já colocado no NVMe. **GO para o controlo numérico do pack C291**. O teste é de exatidão no workload fornecido. O melhor tempo de conversa emparelhado permanece 18,313 s e 5,361 tok/s. [Recibo compacto](result.json) · [Protocolo numérico](numeric-protocol.md)

| Braço no módulo Fedora 620.73.04 | Resolução inicial | Controlo com biblioteca errada | Trabalho físico desta unidade |
|---|---:|---|---|
| C270 × R0 C269 | 18 ELF | Rejeitado | Captura e comparação C127 completas |
| C270 × C291 | 18 ELF | Rejeitado | Listagem e relocação |
| Servidor C281 × R0 C269 | 24 ELF | Rejeitado | Listagem e relocação |
| Servidor C281 × C291 | 24 ELF | Rejeitado | Listagem e relocação |

O processo da captura carregou 21 fornecedores, incluindo os auxiliares tardios identificados no journal. Foram 140 observações dos mapeamentos do próprio PID. O controlo estático anterior abriu 776 419 440 B de ELF distintos nas quatro listagens. Os ficheiros NVIDIA carregados procedem dos pacotes RPM verificados. O ensaio usou a biblioteca de sistema com o módulo do mesmo arranque e a NVML observada no monitor. [Seleção estática](screen.py) · [Supervisão e comparação](numeric.py)

Uma janela C55 e 61 observações C118 antecederam o único arranque do modelo. Foram 36,658 s no relógio do monitor do processo e 97,507 s com a janela C118 e a supervisão. O pico do cgroup foi 16 466 722 816 B, o da RTX 6 882 MiB e o swap zero. Temperaturas máximas de 71,125 °C na CPU, 51,92 °C na GPU e 46,85 °C no NVMe. O processo e o scope terminaram. Os trapézios entre 54 amostras de potência da placa estimam 437,3 J nos 35,965 s cobertos. A energia da máquina completa é desconhecida. A mesma integração no piloto natural anterior do ik estima 2 385,9 J em 146,896 s de cobertura, 223 amostras. Estes gastos correspondem a cargas diferentes. [Monitor e método comum](result.json)

Protocolo estático em `eb51d67a`, execução em `81d50edc`, protocolo numérico em `f58678a5` e captura em `3d03d3f7`. O lote 161 conserva a seleção, o destino e o digest do alias, as duas simulações de RAM, o C55, as amostras, o journal e a captura numérica. Contém 3 299 ficheiros e 89 781 128 B. A reabertura dos originais e dos arquivos voltou a executar a comparação contra C127. Os recibos resultantes coincidiram byte a byte em `9f0cd433586fced6030e790cd3998e85d2d40af74f6ade33461beddd461e85dd`. No portátil, usar `python3 -IB review.py --static "$STATIC" --numeric "$C270" --pilot "$IK_C281" --new-output-dir "$NEW"`. [Verificador](review.py) · [Manifesto 161](../../../private_archive/part-161.json) · [Piloto no manifesto 160](../../../ik_mapped_experts/frontend/server/README.md)
