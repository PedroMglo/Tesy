# Leituras do turno nominal com o histórico real

**NO_GO no cenário M4 a 4,5 GB/s para resolver o prefill só por retenção entre as rotas observadas, mantendo a composição de entrada, 40 slots por camada e os restantes custos do pedido.** O orçamento de 2,430748179 s admite 10 938 366 806 B. Mesmo com conhecimento das rotas e entrega gratuita aos consumidores, o piso de payload do regime é 11 355 292 800 B. Faltam 416 925 994 B. Já no orçamento alternativo que cobra só as 46 avaliações pós-primeiro, a capacidade excede o piso em 333 074 007 B. A passagem de um denominador ao outro explica a diferença. Uma mudança da residência inicial, das fontes de leitura, dos outros custos ou da banda efetiva reabre a conta. A banda é um cenário e estas duas linhas são condicionais. [Conservação e hipóteses](../conservation.md) · [Denominadores](denominadores.md)

**MEDIDO.** Na RTX 4060 Laptop, com os pesos GPT-OSS-120B MXFP4 originais no NVMe interno, cada um dos dois processos C281 completou ambos os POST e fechou a porta. No T2, a sessão reutilizou 2 044 dos 2 197 IDs de entrada e processou os restantes 153 em 5+148. A segunda chamada manteve 32+32+32+32+20. Em cada braço os 78 e 47 IDs amostrados incluíram os EOG corretos. O conteúdo de T1 passou ao histórico de T2 na própria sessão. Os hashes, os canais, os settings e os frames coincidiram com a referência independente. O OFF usa a mesma biblioteca e o mesmo DEBUG5 que ON. M3 permanece PARTIAL e M4 NOT_MET. [Trajetórias de referência](../../../history_lookup/native_ids/README.md) · [Protocolo](protocol.md)

| Braço e turno | Prefill (s) | Decode (s) | tok/s | Primeiro final (s) | Resposta válida (s) |
|---|---:|---:|---:|---:|---:|
| OFF T1 | 61,615 | 19,687 | 3,962 | 80,886 | 81,312 |
| OFF T2 | 10,640 | 9,891 | 4,752 | 20,274 | 20,544 |
| ON T1 | 62,046 | 19,842 | 3,931 | 81,473 | 81,900 |
| ON T2 | 10,746 | 10,004 | 4,698 | 20,486 | 20,761 |

As quatro razões ON/OFF de T2 ficaram entre 1,0099 e 1,0115 na banda prospectiva de 0,85–1,15. Um único par descreve estas sessões. As somas de serviço dão informação sobre o pedido observado. A cronologia de parede e o custo de produto conservam os respetivos relógios.

| Fase ON | Publicações CPU | Publicações CUDA | Bytes devolvidos pelo FD a CPU | Bytes devolvidos pelo FD a CUDA |
|---|---:|---:|---:|---:|
| Prefill 5 | 40 | 11 | 529 272 832 | 145 559 552 |
| Prefill 148 | 768 | 444 | 10 161 643 520 | 5 874 700 288 |
| 46 avaliações de decode | 786 | 305 | 10 399 969 280 | 4 035 563 520 |

O journal contém 55 354 eventos, 48 chamadas, 52 tiles, 2 354 gerações publicadas, 7 062 READ e 7 062 SET. O corte inicial tinha zero slots em carregamento e zero claims. No prefill, 1 263 admissões devolveram 16 711 176 192 B, incluindo alinhamento; 16 695 849 600 B chegaram aos três destinos. Nenhum retorno de READ iniciado por essas duas chamadas ultrapassou o seu fim. Identificaram-se 852 experts distintos ausentes da entrada, pelo menos 11 262 758 400 B; o piso com 40 slots sobe a 859 cargas. A união das leituras nas duas chamadas foi 7,4744 s e a das esperas 7,0167 s. Os intervalos sobrepõem-se. Os bytes do FD O_DIRECT e do SET são grandezas lógicas; para tráfego físico do NVMe é necessária atribuição do dispositivo.

| Hipótese sobre o decode do próprio ON | Orçamento de prefill | Capacidade a 4,5 GB/s | Capacidade menos piso de 859 cargas |
|---|---:|---:|---:|
| M4, 47 tokens em predicted_ms | 2,430748179 s | 10 938 366 806 B | −416 925 994 B |
| AR, 46 avaliações após o primeiro token | 2,597414846 s | 11 688 366 807 B | +333 074 007 B |

O espaço da segunda linha assume atenção, FFN, coordenação e restantes custos da fase gratuitos. As duas contas usam o tempo até ao primeiro conteúdo final da própria execução ON. No nominal histórico independente os dois orçamentos eram 2,424377302 e 2,591043969 s. A diferença exata de 1/6 s corresponde a 750 MB no cenário decimal.

**Proveniência e limites.** A medição decorreu na checkout limpa 912516334740835d7477ec14c086fcf44be7c101. O build reconstruído, os controlos de VMA, as fixtures e o par numérico C270 abriram a sessão. O controlo OFF fechou em 168,574 s e ON em 169,209 s, incluindo C118 fresco de cada PID e cleanup. As janelas do monitor após a admissão duraram 106,453 e 107,184 s. Os picos de cgroup foram 15 745 503 232 e 15 730 016 256 B, respetivamente, com swap zero. A GPU atingiu 6 848 MiB nos dois braços e 56,95/58,61 °C. A CPU atingiu 83,5 °C e o NVMe 50,85/51,85 °C. O monitor não mediu energia por pedido. Cada servidor terminou com código zero após o sinal do proprietário e o supervisor confirmou o fim do PID e do listener.

**Tentativas preservadas.** A primeira C55 recusou o teto E20 por 256 MiB e a reserva de saída de 11 GiB. A segunda recusou a topologia USB da saída. A terceira admitiu E20 no tmpfs após recuperação de capacidade. A primeira identidade ON terminou com EADDRINUSE na sondagem de bind após OFF, com zero launches e sem C118. Antes de ON R02, o mesmo bind passou e a consulta TCP encontrou o porto livre. O estado que o porto tinha no instante da falha fica desconhecido.

**Reprodução.** O controlador aceita um processo por identidade. Usar `profile.py --help` para os caminhos de C55, C270, colocação, build, VMA e fixture e o SHA independente de cada gate. OFF vem antes de ON. A recomendação de produto continua dependente de novos gates.

```sh
python3 -IB compact.py --historical "$C281_R0" --off-dir "$OFF" --on-dir "$ON_R02" \
  --on-r1 "$ON_R01" --c55-r1 "$C55_R01" --c55-r2 "$C55_R02" --c55-r3 "$C55_R03" \
  --precheck "$PRE" --model "$GGUF_NVME" --new-output-dir "$NOVO"
cmp "$NOVO/receipt.json" evidence/receipt.json
```

O compacto revalida os dois prompts e todos os IDs/frames, os monitores, o journal e a conservação por tier, com stat do GGUF e zero leituras de pesos. Os dois replays produziram SHA-256 5820c6549cbdea26426f30bf037addce3a0332d121da377cb9ccca4b19ab25d8 (26 723 B). Os dados naturais ficam no arquivo privado. [Resultado por braço e por chamada](evidence/receipt.json)
