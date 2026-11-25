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
