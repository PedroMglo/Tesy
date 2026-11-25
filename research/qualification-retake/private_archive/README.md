# Recuperação das evidências locais

O arquivo privado do projeto tem a identidade `qualification-20261124-nvme-01`. Cada lote foi publicado sob um nome exclusivo depois de conferir os tamanhos e SHA-256 de todos os ficheiros contra a origem e reler as cópias. A raiz tem permissões 0700 e os ficheiros 0600. O índice com os caminhos das origens permanece dentro do arquivo local.

| Lote | Evidência incluída | Ficheiros | Bytes |
|---|---|---:|---:|
| part-01 | C266 CUDA35 e rows153 com todas as tentativas, colocação, C55 R1, ABBA, canário32 e logs/recibos stock até start R2 | 103 | 687 116 |
| part-02 | Canário28, logs do build, pré-admissão e FAIL R1 antes do spawn | 30 | 122 446 |
| part-03 | C55 R2/R3, pequenos prechecks stock e índice de capturas persistentes do stock, C270 E20 e conversa C281 E20 | 11 | 824 679 |
| part-04 | C55 R5, precheck e quatro processos de 40 slots copiados de tmpfs, mais o índice de 104 ficheiros já persistentes de operadores, canários, colocação e falhas anteriores | 80 | 115 069 544 |

Os [recibos do primeiro lote](part-01.json), [do segundo lote](part-02.json) e [do terceiro lote](part-03.json) contêm o hash do manifesto privado e a contagem por unidade. Na estação que tem o arquivo, apontar `TESY_PRIVATE_ARCHIVE` para o diretório que termina no nome da sua identidade e verificar os lotes.

```sh
python3 -B research/qualification-retake/private_archive/verify.py "$TESY_PRIVATE_ARCHIVE" research/qualification-retake/private_archive/part-01.json
python3 -B research/qualification-retake/private_archive/verify.py "$TESY_PRIVATE_ARCHIVE" research/qualification-retake/private_archive/part-02.json
python3 -B research/qualification-retake/private_archive/verify.py "$TESY_PRIVATE_ARCHIVE" research/qualification-retake/private_archive/part-03.json --project-root "$TESY_PROJECT_STORAGE"
```

Cada entrada do manifesto é um caminho relativo ao lote. O verificador confere a identidade do manifesto antes dos dados e deteta divergências em ficheiros e diretórios. Os raws, o mapeamento dos caminhos pessoais e o registo de reposição da sessão permanecem privados. Os índices públicos não contêm prompts. Os raws de campanhas posteriores recebem lotes novos.

O índice dentro de part-03 contém ainda SHA-256/tamanho de 3 314 ficheiros já persistentes, num total de 90 462 558 B. A opção `--project-root` recebe a raiz física original do projeto que contém as saídas locais em `build/`. Os 3 280 ficheiros de C270 foram verificados no local, sem duplicar a captura. As transcrições da conversa ficam nos outputs privados originais.

O quarto lote conserva os raws completos dos quatro processos a 40 slots, com os dois journals de serviço ON e o witness comum em todos. Os 104 ficheiros no índice externo perfazem 14 078 041 B. Para rever ambos, repetir o comando do terceiro lote indicando `part-04.json` e a mesma raiz física do projeto. [Recibo do quarto lote](part-04.json)

O quinto lote preserva os dois pedidos do stock Aster, os onze ficheiros privados da sonda, o precheck e as falhas de preparação e reprodução. Para verificar os 27 ficheiros (1 826 567 B), usar o comando do primeiro lote com part-05.json. [Recibo do quinto lote](part-05.json)

O sexto lote contém a sonda de oito saídas em E10, o stream privado, o precheck e os dois recibos. O verificador conferiu os nove ficheiros e os 739 444 B. [Recibo do sexto lote](part-06.json)

O sétimo lote conserva o precheck e o FAIL da tentativa stock E20, incluindo a telemetria até à última amostra persistida. O arquivo contém sete ficheiros e 188 795 B. [Recibo do sétimo lote](part-07.json)

O oitavo lote conserva as janelas C55, FAILs, binários congelados, instruções desmontadas, operandos e gold dos dois operadores CPU, os braços físicos e os recibos dos primeiros replays de prefill desta unidade. Os 134 ficheiros totalizam 37 537 825 B. A verificação releu cada ficheiro antes da publicação. [Recibo do oitavo lote](part-08.json)

O nono lote reúne os originais das duas confirmações de cada estudo de cache, a falha de pré-verificação inicial e os ficheiros privados da preparação e do ensaio físico Aster T2. São 24 ficheiros e 4 742 800 B. O verificador confirmou tamanhos e hashes depois da publicação exclusiva. [Recibo do nono lote](part-09.json)

O décimo lote preserva as duas janelas C55 e a respetiva falha, a pré-verificação sem modelo e o arranque físico E20, incluindo os journals e recibos originais. A verificação comparou 14 ficheiros e 248 414 B. [Recibo do décimo lote](part-10.json)

O décimo primeiro lote preserva a janela C55, pré-verificações, telemetria, os quatro pedidos com o 120B e a interrupção anterior ao arranque do primeiro B20. O arquivo tem 57 ficheiros e 4 478 138 bytes. Os três braços E10 que serviram de referência à transferência E20 estão arquivados uma vez. [Recibo do décimo primeiro lote](part-11.json)

O décimo segundo lote reúne 16 ficheiros (1 130 634 B) da fixture de entradas nominais, da janela C55 e da tentativa de conversa no derivado stock. Inclui o stream até aos 180 s, telemetria até ao encerramento e os recibos de falha. [Recibo do décimo segundo lote](part-12.json)

O lote 13 conserva os dois pré-checks, as observações C55/C118, o stream e os dados de encerramento da referência stock para o segundo turno Aster. Foram conferidos 19 ficheiros e 9 283 907 B. [Índice do lote 13](part-13.json) · [Resultado do turno](../aster_fixed_reference/README.md)

O lote 14 preserva a E/S direta, o grafo misto e o manager C291, incluindo as tentativas falhadas. Foram verificadas 16 cópias com 119 481 953 B e 357 ficheiros persistentes com 41 360 553 B. [Índice do lote 14](part-14.json)

O lote 15 conserva os recibos da preparação e do build, os dois binários, as três saídas de CPU0 e as janelas C55/C118. Foram verificados 35 ficheiros e 4 045 766 B. O pack privado de cinco registos ficou no NVMe. [Índice do lote 15](part-15.json)

O lote 16 conserva os dois builds, as duas famílias de 36 braços, a falha C55 inicial, a admissão recuperada e os recibos do teste conjunto de L2. O verificador releu 330 ficheiros com 6 419 091 B. [Índice do lote 16](part-16.json)

O lote 17 preserva a primeira falha de memória e os pares de reprodução do piso de down, da retenção primária e da preparação antes de I. Foram conferidos oito ficheiros com 1 214 708 B. [Índice do lote 17](part-17.json)

O lote 18 guarda a enumeração CUDA, a C55, o grafo misto com o FAIL de bibliotecas e as duas seleções e avaliações independentes de C304. São 32 ficheiros e 10 651 666 B verificados. A ligação simbólica temporária ao driver não duplica a biblioteca da estação. A identidade do ELF e os logs do loader constam dos recibos. [Índice do lote 18](part-18.json)

O lote 19 reúne as seleções e avaliações de desenvolvimento WRT, o cálculo das quatro filas de componentes e a reanálise dos 638 grupos históricos com uma falta. O verificador conferiu dez ficheiros e 122 328 B. [Índice do lote 19](part-19.json)

O lote 20 conserva a nova C55, as três fases da confirmação CUDA usando uma só release de driver e as duas reproduções da escolha de SSD no passo C135. Foram conferidos 27 ficheiros e 10 227 937 B. Os aliases temporários do driver apontavam para objetos pré-existentes do deployment autenticado. [Índice do lote 20](part-20.json)

O lote 21 guarda as duas tentativas de build e os três lançamentos do replay de tokens, com o executável, os recibos idênticos das duas confirmações e os dois incidentes preservados. Foram conferidos 20 ficheiros e 1 407 714 B. [Índice do lote 21](part-21.json)

O lote 22 preserva os mapas privados e as listagens de C270 e C281 nas duas confirmações do loader, bem como a janela física C55. Foram conferidos 12 ficheiros e 148 200 B. [Índice do lote 22](part-22.json)

O lote 23 conserva a preparação e a execução do gate C270 e do par natural C281 após a atualização NVIDIA, e os três ensaios do piso de residência no prefill, incluindo a falha inicial de importação. O verificador conferiu 3 322 ficheiros e 90 189 679 B. Os dois compactos físicos foram reproduzidos a partir das cópias arquivadas. [Índice do lote 23](part-23.json)
