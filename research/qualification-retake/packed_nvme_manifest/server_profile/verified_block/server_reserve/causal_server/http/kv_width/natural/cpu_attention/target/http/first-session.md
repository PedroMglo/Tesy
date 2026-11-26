# Dois turnos naturais do 120B com o pack e a proposta N2/M2

**MEDIDO.** O cliente do Tesy completou ambos os pedidos, com o GGUF original no NVMe e os mesmos 78/47 IDs da referência independente, incluindo EOG. Em T2 o target recuperou 2 044 posições do primeiro turno e processou 153 novas. O primeiro conteúdo final demorou **19,007 s**, a validação **19,279 s** e o decode produziu **4,941 tok/s**. O melhor T2 anterior com o pack em modo serial foi 18,313 s e 5,361 tok/s. M3 PARTIAL e M4 NOT_MET. [Protocolo físico](protocol.md) · [Controlo serial e baseline em duas ordens](../../../../../../../../../conversation/ordens.md)

| Turno e braço | IDs | Verificações | Propostos / aceites | Prefill (s) | Decode (s) | tok/s | Primeiro final (s) | Válido (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| T1 ON | 78 | 9 | 18 / 11 | 57,768 | 17,841 | 4,372 | 74,973 | 75,621 |
| T2 ON | 47 | 11 | 22 / 12 | 9,741 | 9,512 | 4,941 | 19,007 | 19,279 |

A família fechou em **FAIL** ao importar o resumo do cliente depois do encerramento. ON teve um processo e dois pedidos. OFF (mesma biblioteca serial), P (C291 histórico com pack) e R (R0) ficaram NOT_RUN. Faltaram no recibo as observações de descritores e os instantes do sinal que o controlador mantinha em memória. O cliente guardou as respostas e os terminais e o monitor registou saída zero do modelo após paragem pelo proprietário. O pico da RTX foi 6 854 MiB com zero swap no cgroup. Decorreram 162,351 s na família e 99,711 s no processo observado. O efeito causal sobre o tempo aguarda os controlos do mesmo ensaio.

O teste sem modelo reproduziu a colisão de dois módulos Python chamados `measure`. O leitor isolado recuperou todos os campos e tempos da implementação original em intérprete independente e recusou o journal sem terminal. A revisão confirmou cada grupo aceite ou rejeitado contra a agenda pré-registada, a integridade dos inputs e a conservação dos IDs. O tamanho da parte 184 é 1 699 248 B em 45 ficheiros. A revisão na origem e no arquivo privado teve SHA-256 `1625bd50519896b2c6214c5ea664571cf8fec41eaa53f46c17335ea3bc17d714`. [Resultado reaberto](report-result.json) · [Prova e código](report.py) · [Manifesto](../../../../../../../../../../../private_archive/part-184.json) · [Condições da repetição](report_protocol.md)
