# Retoma da verificação de proveniência

A primeira identidade `ready-slot-lifetime-20261127-01`, commit `17bb22017286e4212925e21b1d4e522201f9c631`, árvore `edeef9dc5ab88268ebacae450b14226d4eadcd23`, encerrou antes de ler ambos os PFJ. Sob o teto de espaço virtual de 512 MiB, a inspeção paralela do índice Git falhou ao criar uma thread. O recibo de falha tem SHA-256 `41a1f349b4c120f18e70711f8d34dd341eb512dd2ec8f9ebd88792c120b57d10`, duração 0,07 s e RSS máximo 21 592 KiB.

O pré-voo com `git -c core.preloadIndex=false -c index.threads=1 status --porcelain` confirmou a árvore limpa com o mesmo limite. Usar esta configuração apenas no processo da inspeção Git, registar primeiro o HEAD e a árvore e abrir os destinos 02 e 03. Mantêm-se o protocolo, os custos, as entradas e os limites da campanha. [Protocolo congelado](slot-lifetime.md)
