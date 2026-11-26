# A cache altera a melhor sequência de verificações?

**NO_GO para combinar estes três bancos com as 35 recuperações e os custos disponíveis.** A pesquisa agora admite todos os caminhos compatíveis das duas agendas. A melhor margem conjunta com 35 continua negativa. No cenário mais favorável, a retenção pela frequência projeta **10,066 s** ao primeiro final e **5,990 tok/s**. No cenário com os preços seriais do mesmo processo, a melhor margem com as 35 fica **401,537 ms** aquém. Trata-se de uma projeção condicional que já concede o prefill ao piso de serviço do NVMe. No portátil, o melhor decode nominal dos pares do pack continua em 5,361 tok/s. [Protocolo](joint-protocol.md) · [Caminhos e preços completos](joint-result.json)

| Preço individual | Banco de T1 | Recuperações de prefill | Melhor margem conjunta a 100% | Primeiro final / tok/s no mesmo caminho | Exposição mínima para os dois alvos |
|---|---|---:|---:|---|---:|
| SERIAL | Recência | 35 | −506,718 ms | 10,507 s / 5,845 | Excede 100% |
| SERIAL | Misto | 35 | −442,078 ms | 10,442 s / 5,761 | Excede 100% |
| SERIAL | Frequência | 35 | −401,537 ms | 10,402 s / 5,744 | Excede 100% |
| Menor observado | Recência | 35 | −170,687 ms | 10,171 s / 6,100 | Excede 100% |
| Menor observado | Misto | 35 | −106,047 ms | 10,106 s / 6,008 | Excede 100% |
| Menor observado | Frequência | 35 | −65,506 ms | 10,066 s / 5,990 | Excede 100% |
| Menor observado | Recência | 230 | +216,594 ms | 9,710 s / 6,171 | 33,5886% |
| Menor observado | Misto | 230 | +104,943 ms | 9,678 s / 6,081 | 51,0731% |
| Menor observado | Frequência | 230 | −12,585 ms | 9,654 s / 5,990 | Excede 100% |

A margem conjunta é o menor dos saldos temporais na mesma sequência. A coluna de débito usa 47 IDs incluindo EOG. Nos preços de SERIAL, conceder as 230 recargas também deixa os três bancos aquém dos dois alvos. O melhor dos três é o de recência, com margem de −119,437 ms. Entre as combinações estudadas, a margem positiva depende simultaneamente das 230 recuperações hipotéticas, dos preços individuais mais favoráveis entre braços, de suficiente exposição do serviço e de retenção por recência ou mista. O artigo de DISCO avalia quanta especulação autorizar. Neste experimento, mudar qual passo é barato altera as alternativas que precisam de ser comparadas no mesmo pedido. [Precedentes e diferenças de regime](../../../../../../../../../../../../../post-c320/literatura.md)

Em cada passo individual compatível, a cache pode retirar até a fração especificada do custo dos experts que teria servido na call correspondente, limitado à duração do próprio passo. O algoritmo refaz os caminhos mínimos no grafo com os preços assim calculados. Conserva o preço dos grupos verificados e desconta uma única vez cada geração de prefill. A ablação vazia reproduziu a fronteira anterior. A fixture pequena exigiu mudar de bloco para serial após descontar o serviço. Nos testemunhos reais decisivos, o ótimo continuou a pertencer à fronteira anterior. O cálculo com frações exatas apertou de 510 730 para 510 731 ppm o limiar do misto no cenário de 230. A diferença de um ppm vem do arredondamento favorável a nanossegundos da parte 195. [Cálculo anterior e aquisições de T1](bank.md) · [Método](joint.py)

O resultado aconselha mudar a escolha das 353 identidades ou o serviço primário antes de investir nestas três receitas como solução. Não se mediram poupanças físicas pela nova composição. Com a seleção, uma pergunta seguinte é se as próprias ofertas disponíveis em T1 permitem compor um banco que abra margem aos preços de SERIAL com as 35 recuperações. Isso distingue falta de capacidade de falta de informação causal ao selecionar.

Os dois replays ocorreram na árvore limpa de `bb70eef388cd0b37c367afe0357fa4c3c2bdbd89`. Demoraram 4,805 e 4,812 s e atingiram 118,4 e 118,3 MiB, zero swap, GPU ou pedidos novos. O arquivo 196 contém quatro ficheiros e 41 026 B. O SHA-256 do resultado é `730ca17f999f9b5de4739675bba6e2232f44334638be9686961588158205972f`. [Recibo do arquivo](../../../../../../../../../../../../private_archive/part-196.json)

```sh
python3 -IB "$STUDY/joint.py" --archive "$AR" \
  --family "$AR/part-193/tesy-c281-context-http-20261126-r02" \
  --lookup-run "$AR/part-192/tesy-c281-native-context-20261126-r02" \
  --capture "$AR/part-29/tesy-natural-ids-capture-20261125-r01" \
  --verified "$AR/part-29/tesy-natural-ids-verified-20261125-r01" \
  --plan "$AR/part-177/tesy-packed-causal-plan-20261126-r03" \
  --commit bb70eef388cd0b37c367afe0357fa4c3c2bdbd89 --new-output-dir "$NEW"
```
