# O pack de experts na conversa natural do 120B

**MEDIDO no portátil, 25 de novembro.** No segundo turno, com a mesma biblioteca C291, o pack contíguo antecipou o primeiro conteúdo final de 21,414 para 18,515 s (−13,54%). O ganho observado abrange 1,571 s de prefill e 1,360 s de decode. O R0 independente mediu 21,054 s. O modelo original e o pack já estavam no NVMe interno em ambos os contrastes. R e O leem o GGUF, P lê os mesmos três componentes de cada expert pelo pack verificado. Cada processo abriu uma conversa completa com histórico. [Pré-registo](protocol.md) · [Recibo com os seis pedidos](evidence/rop-r02.json)

**Decisão.** GO para testar o ganho do componente na ordem oposta e integrá-lo numa combinação que conserve os pesos e o trabalho. NO_GO para a suficiência deste braço na ordem R/O/P. O pack ficou em 5,263 tok/s, com ambos os alvos nominais por cumprir. Na hipótese de cortar o decode de 8,930 s para 47/6 = 7,833 s, conservar a cauda depois do primeiro final e creditar toda a poupança antes dele, esse primeiro final ainda demoraria 17,417 s. O ensaio C293 a trabalho fornecido mantém a decisão segundo os seus próprios limiares. M3 PARTIAL e M4 NOT_MET. Um outro caso, dispersão entre ordens, contexto efetivamente exercitado e a prova sustentada fazem parte da qualificação posterior. [Contrato de custo](../product-protocol.md) · [O que a interface HTTP pode custar](relogios.md)

## Conversa natural R/O/P

Cada processo recebeu os mesmos dois pedidos. T1 avaliou 2 043 IDs de prompt e produziu 78 IDs, com 77 ecos no batch seguinte e 71 frames SSE. T2 teve 2 044 IDs em cache, 153 novos e 47 gerados, com 46 ecos e 40 frames. A revisão recuperou a mesma sequência de IDs, conteúdo dos canais e validação dos dois turnos nos três processos. Cada preço de decode usa a contagem publicada pelo servidor, 78 ou 47, incluindo o token proveniente do prefill.

| Pedido | Braço | 1.º final (s) | Transporte (s) | Válido (s) | Prefill (s) | Decode (s) | Tok/s | Válido − servidor (ms) |
|---|---|---|---|---|---|---|---|---|
| T1 | R | 84,354 | 84,806 | 84,808 | 64,365 | 20,429 | 3,818 | 13,601 |
| T1 | O | 84,477 | 84,921 | 84,924 | 64,425 | 20,485 | 3,808 | 13,564 |
| T1 | P | 78,412 | 78,795 | 78,797 | 60,846 | 17,938 | 4,348 | 12,634 |
| T2 | R | 21,054 | 21,351 | 21,355 | 11,023 | 10,317 | 4,555 | 14,309 |
| T2 | O | 21,414 | 21,699 | 21,701 | 11,393 | 10,291 | 4,567 | 17,240 |
| T2 | P | 18,515 | 18,763 | 18,766 | 9,822 | 8,930 | 5,263 | 13,397 |

O residual de relógios é a duração até à validação menos prefill e decode somados. A parcela até fechar o transporte e a validação posterior somam exatamente esse residual. A coluna do primeiro frame é uma observação auxiliar em dois relógios. O endpoint conserva a duração de serviço da E/S como desconhecida.

| Pedido | Braço | 1.º SSE − prefill (ms) | Transporte − (prefill + decode) (ms) | Válido − transporte (ms) | Transporte após 1.º final (ms) |
|---|---|---|---|---|---|
| T1 | R | 10,450 | 10,967 | 2,634 | 451,350 |
| T1 | O | 9,639 | 10,877 | 2,687 | 444,330 |
| T1 | P | 9,610 | 10,349 | 2,285 | 382,885 |
| T2 | R | 9,192 | 10,327 | 3,982 | 296,591 |
| T2 | O | 13,869 | 14,614 | 2,626 | 284,363 |
| T2 | P | 9,670 | 10,605 | 2,792 | 248,279 |

**Contrastes observados.** Nas colunas de segundos, o sinal positivo indica tempo poupado ao passar do primeiro braço para o segundo. Na coluna de tok/s indica aumento da taxa. R→O troca a biblioteca com o pack desligado. O→P mantém a biblioteca e ativa o pack.

| Pedido | Passagem | 1.º final (s) | Transporte (s) | Válido (s) | Prefill (s) | Decode (s) | Tok/s |
|---|---|---|---|---|---|---|---|
| T1 | R→O | -0,122 | -0,115 | -0,115 | -0,059 | -0,056 | -0,010 |
| T1 | O→P | +6,065 | +6,126 | +6,127 | +3,578 | +2,547 | +0,541 |
| T1 | R→P | +5,942 | +6,011 | +6,011 | +3,519 | +2,491 | +0,530 |
| T2 | R→O | -0,360 | -0,348 | -0,346 | -0,370 | +0,026 | +0,012 |
| T2 | O→P | +2,900 | +2,936 | +2,936 | +1,571 | +1,360 | +0,696 |
| T2 | R→P | +2,540 | +2,588 | +2,589 | +1,202 | +1,387 | +0,707 |

No T2 do pack, a distância aos alvos do bloco foi de 8,515 s até ao primeiro final e 0,737 tok/s no decode.

**Envelopes por processo.** RSS, cgroup e VRAM são picos. A integração trapezoidal usa apenas pares adjacentes de potência observada no mesmo PID e GPU. A cobertura indica o intervalo de integração sobre a duração total do monitor.

| Braço | READY (s) | RSS / cgroup (GiB) | VRAM (MiB) | CPU / GPU / NVMe (°C) | GPU média / máxima (W) | GPU (J) | Cobertura / monitor (s) | n |
|---|---|---|---|---|---|---|---|---|
| R | 4,129 | 14,860 / 15,100 | 6848 | 83,50 / 58,58 / 52,85 | 13,55 / 16,64 | 1497,9 | 110,564 / 111,283 | 161 |
| O | 3,900 | 14,906 / 14,725 | 6848 | 83,50 / 58,38 / 53,85 | 13,85 / 17,21 | 1531,6 | 110,597 / 111,320 | 162 |
| P | 4,016 | 14,914 / 14,719 | 6848 | 83,50 / 58,70 / 54,85 | 14,21 / 16,46 | 1445,0 | 101,705 / 102,745 | 149 |

| Braço | C118 (s) | Frescura em Popen (s) | SIGINT → pidfd (ms, intervalo) | pidfd → porta e scope verificados (ms) | Último corte → limpeza (s) | Envelope do braço (s) |
|---|---|---|---|---|---|---|
| R | 60,187 | 0,053 | 705,471–705,481 | 320,092 | 1,026 | 173,048 |
| O | 60,148 | 0,052 | 702,400–702,407 | 166,392 | 0,869 | 173,047 |
| P | 60,165 | 0,062 | 690,340–690,349 | 566,992 | 1,258 | 164,546 |

Cada processo teve 20 GiB de cgroup, paragem preventiva a 19,5 GiB e zero swap. Os três terminaram com código 0 sob SIGINT do proprietário, unidade encerrada e porta disponível. O mesmo descritor de pack O_DIRECT só apareceu em P nos dois cortes. A energia do anfitrião e os tempos individuais de join dos quatro workers continuam desconhecidos. O bloco executado na ordem R/O/P durou 631,518 s e contém uma observação por braço, sem estimativa de dispersão.

Revisão independente a partir dos três recibos terminais e dos seus ficheiros privados. SHA-256 da família `d3c4a498b0b774e70c281134fea885a3189fe8a81304f7bd1f2b7d9d321a0c4b`.

## Proveniência, custos e falhas preservadas

A preparação anterior ao modelo, o SHA da árvore e os hashes do runtime ficaram fixados antes da medição. R02 usou o commit `7aae40d22a2fe466a7ab5e25a717cfb65dcf60e5`. A janela C55 foi admitida à terceira tentativa. Nas duas primeiras, a disponibilidade de memória ficou 97 148 928 B e 86 290 432 B aquém da margem. A recuperação transferiu artefactos Tesy de campanhas encerradas do tmpfs para o arquivo, com verificação de conteúdo. O primeiro bloco R01 iniciou um servidor e completou dois pedidos. Em T2 mediu 21,398 s e 4,551 tok/s. O arranque seguinte recusou a porta ainda ocupada. A família terminou nesse ponto. R02 começou de novo a partir de R. As esperas de 60,545 e 59,529 s até à disponibilidade da porta estrita pertencem ao envelope da campanha. [Falha R01 e diagnóstico TCP](interarm.md) · [Janelas físicas e preparação R01](evidence/archive-76.json) · [R01 e preparação R02](evidence/archive-77.json)

R02 usou três processos de modelo, seis POST e 631,518 s dos 1 950 s previstos. Incluindo R01 foram quatro processos e oito pedidos. O arquivo da parte 78 contém 104 ficheiros e 5 145 769 B, incluindo duas revisões. Ambas demoraram 0,18 s. Uma terceira reprodução usando as cópias de arquivo das partes 23 e 78 demorou 0,14 s. As três produziram o mesmo SHA-256 `290c4a88d650899a90fbeda9a5de4043ad404783d4bccb94b66fff982949b261`. [Reprodução e argumentos](reproduzir.md) · [Manifesto de arquivo](evidence/archive-78.json)
