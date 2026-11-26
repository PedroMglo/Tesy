# Quanto se pode somar nos blocos de decode ao preço observado?

**NO_GO para chegar aos dois alvos com os despachos medidos e o prefill atual.** No T2, até escolhendo com conhecimento do futuro entre todos os blocos das duas políticas e o passo serial mais rápido já observado em cada posição, o melhor decode projetado é **5,917 tok/s**. Faltam 110 ms até às 47 saídas a 6 tok/s. O menor tempo ao primeiro conteúdo final é **17,502 s**, noutro caminho. Esta conclusão aplica-se aos custos transportados entre posições que já foram executadas. O melhor débito emparelhado medido no portátil continua em 5,361 tok/s. [Protocolo anterior ao cálculo](envelope-protocol.md) · [Resultados e caminhos completos](envelope-result.json) · [Quatro processos físicos](http.md)

| Preço de passos sem proposta | Melhor relógio escolhido em T2 | Decode (s) | tok/s | Primeiro final (s) | Prefill admissível para 10 s (s) |
|---|---|---:|---:|---:|---:|
| SERIAL | Primeiro final | 8,382193 | 5,607 | 17,838023 | 1,855592 |
| SERIAL | Decode | 8,278910 | 5,677 | 17,876813 | 1,816802 |
| Menor preço observado na posição | Primeiro final | 8,046162 | 5,841 | 17,501992 | 2,191623 |
| Menor preço observado na posição | Decode | 7,942879 | 5,917 | 17,540782 | 2,152833 |

**TRACE_DERIVED.** O caminho de menor tempo ao primeiro final contém cinco verificações. O de menor decode acrescenta uma sexta, escolhida depois de 43 IDs já confirmados. Essa troca economiza 103,283 ms no decode e atrasa o primeiro final em 38,790 ms. Somar as duas melhores marcas daria uma receita impossível. Mantendo para os passos individuais o preço de SERIAL, o melhor decode pouparia 0,537 s face aos 8,815434 s desse processo. O ganho permanece uma hipótese de composição. A troca de política pode mudar os experts que ficam residentes, o trabalho posterior e o tempo observado.

T1 teve 78 saídas e primeiro final na 76.ª amostra. Com os passos individuais de SERIAL, um caminho compatível melhoraria condicionalmente os dois relógios para 17,075390 s de decode e 74,184966 s até ao primeiro final. Com preços seriais escolhidos entre braços, os valores seriam 16,562335 e 73,671911 s. A proteção de T1 do filtro realmente executado falhou no par com SERIAL. Em T2 houve dois blocos idênticos nas duas receitas, com diferenças de preço de 8,299 e 18,139 ms. Nas 30 posições com mais de um preço de passo serial, a amplitude foi de 2,884 a 66,065 ms. O cenário mais favorável concede gratuitamente a melhor dessas observações.

## Que redução ainda faltaria no prefill?

A contabilidade do kernel no prefill do próprio SERIAL fica entre **14 623 408 128 e 18 325 536 768 B**. A incerteza sobre a origem do relógio do monitor após integrar o encerramento foi de 356,387 ms. Concedendo o caminho de primeiro final mais favorável, a 4,5 GB/s caberiam no máximo 9 862 305 264 B nos 2,191623 s. A redução mínima é **4 761 102 864 B**. Esta hipótese cobra só o volume que tem de ser servido no intervalo e dá gratuitamente o restante trabalho.

| Crédito alternativo de prefill | Falta de volume no caminho de primeiro final mais rápido | Falta no caminho de maior débito |
|---|---:|---:|
| 35 recuperações compatíveis nos 40 slots | 4 298 336 784 B | 4 472 891 784 B |
| Todas as 230 recargas de 148 | 1 720 068 624 B | 1 894 623 624 B |

Os dois créditos pressupõem a mesma população de recargas nos journals P97/P106 e nesta conversa, redução física de todos os bytes alinhados e ausência de custo adicional exposto. As 35 fazem parte das 230. Os mesmos IDs confirmados em todas as conversas não identificam as leituras individuais no processo SERIAL. O caminho mais favorável ainda requer retirar pelo menos outros 1,720 GB do intervalo de prefill e alterar o preço ou o conjunto de ações de decode. Um próximo teste pode identificar primeiras faltas servíveis por bytes já disponíveis ao terminar T1 e confrontar a cobertura conjunta com esse saldo. [Prova nos 40 slots](../slots.md) · [População de 230 recargas](../reloads.md) · [Método dos contadores](../io.md)

## Reprodução

O grafo percorre 46 transições em T2 e 77 em T1. Cada ação cobra o seu intervalo no relógio de um só produtor. O cálculo reaplica os deltas ao cliente e ao servidor SERIAL nas respetivas unidades. A fixture tem três caminhos, dois não dominados, confirmados por enumeração exaustiva. O verificador reconstrói os três braços puros, confere ambas as somas e verifica as desigualdades de caminho mínimo em todas as arestas. O recibo identifica as 64/117 arestas em T2 e os despachos de cada testemunho. [Verificador](envelope.py)

O protocolo e o código foram fixados em `3b73a17e24a79f8c7105067904110b064d0fab0a`. Os runs sobre os originais e sobre o arquivo demoraram 1,198 e 1,171 s, com picos de 64,5 e 63,2 MiB e zero swap, novos forwards ou pedidos. As duas saídas deram SHA-256 `1d19912281e2ca9502bd00c7587d18c50e246aa7a3cb3c96c6ec91cd2f0aa35f`. A parte 194 preserva quatro ficheiros, 104 558 B. [Recibo do arquivo](../../../../../../../../../../../../private_archive/part-194.json)

```sh
python3 -IB "$STUDY/envelope.py" \
  --family "$AR/part-193/tesy-c281-context-http-20261126-r02" \
  --lookup-run "$AR/part-192/tesy-c281-native-context-20261126-r02" \
  --review-sha256 969326ae832d6a968981f5931a08d437e29ecdbcba6ed94a7a63887358266dd0 \
  --commit 3b73a17e24a79f8c7105067904110b064d0fab0a \
  --new-output-dir "$NEW"
```

Para reproduzir o resultado de campanha, usar uma worktree limpa do commit acima. O protocolo e o resumo físico da parte 193 já pertencem a essa árvore.
