# Custo da proposta de dois tokens na conversa com histórico

**NO_GO para ativar N2/M2 neste nominal.** O mesmo servidor e a mesma biblioteca, com o pack, produziram 5,158 tok/s em serial e 4,754 tok/s com a proposta. No T2 a intervenção atrasou o primeiro conteúdo final em 0,765 s. Em T1 também atrasou o primeiro final e o decode. Os quatro processos independentes passaram ambos os validadores. A qualificação do ensaio é GO diagnóstico. M3 permanece PARTIAL e M4 NOT_MET. [Protocolo de produto](protocol.md) · [Protocolo da repetição](report_protocol.md) · [Comparação compacta](family-result.json)

| Braço | Turno | Prefill (s) | Decode (s) | tok/s | Primeiro conteúdo final (s) | Resposta válida (s) |
|---|---|---:|---:|---:|---:|---:|
| ON, pack e proposta | T1 | 61,116 | 18,342 | 4,253 | 78,791 | 79,470 |
| OFF, mesma biblioteca serial | T1 | 60,195 | 18,178 | 4,291 | 77,989 | 78,385 |
| P, C291 independente com pack | T1 | 61,045 | 18,235 | 4,277 | 78,891 | 79,294 |
| R, C269 de referência | T1 | 65,376 | 20,166 | 3,868 | 85,106 | 85,554 |
| ON, pack e proposta | T2 | 10,064 | 9,887 | 4,754 | 19,677 | 19,968 |
| OFF, mesma biblioteca serial | T2 | 10,047 | 9,112 | 5,158 | 18,912 | 19,173 |
| P, C291 independente com pack | T2 | 9,967 | 9,157 | 5,133 | 18,882 | 19,140 |
| R, C269 de referência | T2 | 11,158 | 10,219 | 4,599 | 21,097 | 21,391 |

O cliente recebeu dois turnos naturais em cada processo, com 78 e 47 IDs confirmados incluindo EOG. T2 reutilizou 2 044 posições e acrescentou 153. O revisor reabriu todos os IDs, profundidades de aceitação, conteúdos validados, cortes vivos e provas de encerramento. A primeira observação ON, preservada na parte 184, deu 19,007 s e 4,941 tok/s em T2. O melhor resultado emparelhado anterior com pack mantém 18,313 s e 5,361 tok/s. O ensaio tem uma ordem e usa o observador DEBUG. O caso de código, os pares trace-OFF do avaliador e a sessão sustentada permanecem NOT_RUN nesta receita. Os cortes históricos de redução do decode de 17,62% nominal e 18,02% código pertencem à via C318 dos quatro pares de trabalho fornecido. [Primeira observação e desvio do relatório](first-session.md)

## O que ganhou e perdeu tempo

No relógio nativo do mesmo processo, o revisor alinha as posições inicial e final de cada grupo com as mesmas posições de OFF. As 46 transições de T2 conservam exatamente o intervalo entre a primeira amostra e EOG. O resíduo entre o decode do servidor e esse intervalo é +1 μs em OFF e −11 μs em ON. Os relógios de cliente, GPU e servidor são conservados separadamente.

| Grupo de T2 | Grupos | IDs no intervalo | ON (s) | OFF nas mesmas posições (s) | OFF − ON (s) |
|---|---:|---:|---:|---:|---:|
| Serial entre propostas | 23 | 23 | 4,567384 | 4,660673 | +0,093289 |
| Ambos aceites | 6 | 18 | 3,173182 | 3,628051 | +0,454869 |
| Primeiro rejeitado | 5 | 5 | 2,146884 | 0,823556 | −1,323328 |

As seis verificações com aceitação completa foram mais rápidas que as respetivas sequências seriais. As cinco rejeições foram mais lentas. Com a escolha perfeita apenas entre os grupos já medidos, mantendo os restantes custos e a residência de OFF, o decode projetado é 8,657412 s ou 5,429 tok/s. Para o primeiro delta final, produzido na amostra 45, o crédito máximo pelos blocos já medidos é 0,358642 s. O primeiro final ficaria em 18,553664 s. Mantendo esse decode e o exterior, o prefill teria de caber em **1,493071 s** para cumprir 10 s. Esta conta condicional dá crédito à melhor escolha em cada grupo observado. Reordenar verificações pode mudar os pools e criar grupos ainda sem preço. A próxima regra usa apenas história já confirmada. [Protocolo do filtro](context-protocol.md)

## Proveniência e reprodução

A medição usou o commit `7b4c40c3a976037a3d6c75da359a959fca41bcc4`, o mesmo C55 e o ELF `45f509221f21188cd9d2b7808b08e47a7405e3c66ed82a68402bbad0f4af6b43` em ON/OFF. A preparação fixou quatro comandos em `96fff2c7ab0116b6948766acead2c781d8fa2cc6c7196154812facd08fcf74c2`. A família durou 853,122 s e guardou quatro inventários C118 de 61 amostras. O cgroup atingiu no máximo 14,894 GiB sob cap E20, com zero swap. A RTX atingiu 6 854 MiB. A energia estimada da GPU foi 1 463,5 / 1 494,8 / 1 465,3 / 1 539,1 J em ON/OFF/P/R. O tempo desde o sinal de encerramento até à confirmação do cleanup foi 823 / 1 191 / 716 / 757 ms. As esperas entre servidores para o porto de loopback somaram 180,632 s fora dos pedidos.

Os originais e o arquivo privado reproduziram o mesmo SHA-256 `aa1f06224bfa702e79d5c351b94b11a51c2978436b37780cf021e880cf07f1df`. O primeiro resumo local tinha calculado também para T1 o orçamento nominal de 10 s. O resumo publicado aplica esse limiar só a T2. Todos os tempos medidos coincidem nas duas revisões. A parte 185 guarda 145 ficheiros, 6 823 712 B. [Manifesto privado](../../../../../../../../../../../private_archive/part-185.json) · [Revisor](review_family.py)

```sh
python3 -IB "$HTTP/review_family.py" \
  --prepared "$AR/part-185/tesy-c281-cpu-rows-prepared-20261126-r02" \
  --family "$AR/part-185/tesy-c281-cpu-rows-http-20261126-r02" \
  --capture "$AR/part-29/tesy-natural-ids-capture-20261125-r01" \
  --verified "$AR/part-29/tesy-natural-ids-verified-20261125-r01" \
  --plan "$AR/part-177/tesy-packed-causal-plan-20261126-r03" \
  --new-output-dir "$NEW_REVIEW"
```

`HTTP` é o diretório deste documento. `AR` é a raiz privada qualification-20261124-nvme-01. O destino da revisão deve ser novo.
