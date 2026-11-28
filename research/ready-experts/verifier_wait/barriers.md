# Quanto custa ter os experts prontos na verificação de três posições?

**INCONCLUSIVE para a alteração que só elimina a espera final pelos experts dentro do verificador.** A execução física localizou 3,276 s nessa barreira em nove blocos que levaram 4,314 s até à sincronização. O décimo bloco atravessa a primeira peça final e também tem de ser pago. Com os dois controlos sem observador, o braço observado, os dois W e os dois custos de prefill simulados, o primeiro conteúdo ficaria entre **9,681 e 10,054 s**. Vinte das 24 combinações de preços satisfazem os dois cortes. São combinações dos mesmos processos e dos dois replays do proponente. A dispersão atravessa o alvo de 10 s. R0 continua a ser o controlo operacional. [Protocolo e critérios](protocol.md) · [Recibo dos quatro braços](evidence-20261128-r01/barriers.json)

### Onde apareceram os segundos

O portátil executou o target original, com 2 044 posições de histórico reutilizadas, 153 novas e 47 IDs até EOG. O primeiro fragmento final da referência sai na amostra 45. O profiler lê o contador nativo sob o mutex depois de sincronizar cada chamada. O remap espera até os quatro experts selecionados ficarem residentes. Essa espera inclui o serviço que atrasou o consumidor, desde a entrega dos pesos à cópia e ao despertar. Os bytes abaixo são pedidos lógicos do pack e as janelas alinhadas são calculadas a partir do formato e das cargas completas.

| Passos de T2 | Chamadas | Tempo sincronizado | Barreira final | Cargas do pack |
|---|---:|---:|---:|---:|
| S, decode serial completo | 46 | 8,761 s | 6,482 s | 1 091 |
| B1, verificação e passos seriais | 34 | 9,397 s | 7,001 s | 1 196 |
| B1, seis blocos com as duas propostas aceites | 6 | 2,955 s | 2,273 s | 394 |
| B1, cinco blocos com a primeira proposta rejeitada | 5 | 1,984 s | 1,415 s | 241 |

Nos seis blocos aceites, o percurso serial nas mesmas posições exigiu 433 cargas. Nos cinco rejeitados exigiu apenas 87. A execução das três linhas ativou 2 095 e 1 648 pares distintos de camada/expert, respetivamente. As 3 743 ativações distintas já foram deduplicadas antes de reservar slots. A diferença para os 4 752 usos linha/rank conta possíveis reutilizações de pesos pelo cálculo. O efeito líquido de toda a agenda foi **mais 105 cargas** face ao serial, aproximadamente 1,388 GB de payload. O S mediu nos prefills de 5 e 148 posições, respetivamente, 0,453 e 8,786 s, com 0,299 e 5,584 s nas barreiras. Os relógios do cliente, da verificação dos logits e de cleanup são distintos destes intervalos.

| Verificação | Nove blocos completos antes da peça | Dez blocos incluindo o que a produz | Onze no decode | Primeiro conteúdo depois do crédito condicional |
|---|---:|---:|---:|---:|
| B0a, observador desligado | 4,302 s | 4,663 s | 4,930 s | 9,746–10,046 s |
| B1, observador ligado | 4,314 s | 4,671 s | 4,939 s | 9,754–10,054 s |
| B0b, observador desligado | 4,241 s | 4,598 s | 4,872 s | 9,681–9,981 s |

A neutralidade passou a tolerância prospetiva de ±10% contra cada B0. Os dois prefills alternativos continuam a ser os pisos condicionais de 4,104 e 4,197 s. Retirando apenas a barreira dos B3, o decode composto ficaria em 5,676–5,950 s. O resto do tempo de cada bloco inclui cálculo e trabalho do runtime. Uma medição por operação ainda seria necessária para repartir esse resto entre kernels, despacho e memória.

Em S foram verificados os hashes dos 47 vetores completos e finitos de 201 088 logits. Cada B produziu 57 vetores, com comparação de todas as linhas consultadas a S e de todas as linhas descartadas entre os três B. Houve quatro cortes bitwise de KV em cada processo. No primeiro intento, S, B0a e B1 fecharam com telemetria. B0b parou na C118 após a primeira amostra, antes de criar o processo do modelo. O segundo controlo foi observado num arranque independente, com nova C55 e o mesmo ELF. A falha original permanece no arquivo. [Protocolo da recolha independente](completion.md)
