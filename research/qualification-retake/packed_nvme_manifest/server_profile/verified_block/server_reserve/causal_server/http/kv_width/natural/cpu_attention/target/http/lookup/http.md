# Filtro de contexto no servidor e preço dos novos blocos

**NO_GO para ativar este filtro no nominal.** No mesmo binário com pack, o filtro chegou a 5,213 tok/s e o serial a 5,332. O cliente esperou mais 0,243 s pelo primeiro final e mais 0,114 s pela resposta válida com o filtro. Na comparação com a proposta fixa, o filtro adiantou o primeiro final em 0,198 s e o decode em 0,391 s. A proteção de T1 também falhou contra o serial nos dois relógios. Esta é uma família diagnóstica em ordem única com o 120B original. M3 permanece PARTIAL e M4 NOT_MET. [Protocolo anterior ao ensaio](http-protocol.md) · [Recibo por braço](http-result.json)

| Braço | Turno | Prefill (s) | Decode (s) | tok/s | Primeiro final (s) | Válido (s) |
|---|---|---:|---:|---:|---:|---:|
| Filtro | T1 | 58,589 | 17,878 | 4,363 | 76,090 | 76,479 |
| Proposta fixa | T1 | 57,952 | 17,899 | 4,358 | 75,201 | 75,862 |
| Serial com pack | T1 | 57,463 | 17,546 | 4,445 | 74,655 | 75,024 |
| R0 com GGUF | T1 | 61,897 | 19,653 | 3,969 | 81,132 | 81,562 |
| Filtro | T2 | 9,606 | 9,016 | 5,213 | 18,514 | 18,637 |
| Proposta fixa | T2 | 9,562 | 9,406 | 4,997 | 18,712 | 18,983 |
| Serial com pack | T2 | 9,694 | 8,815 | 5,332 | 18,271 | 18,523 |
| R0 com GGUF | T2 | 10,704 | 9,883 | 4,756 | 20,329 | 20,601 |

Os quatro processos receberam 2 043 posições em T1 e reutilizaram 2 044 de 2 197 em T2. O target confirmou os mesmos 78 e 47 IDs greedy completos, incluindo EOG, e os oito pedidos passaram os validadores e a verificação de prefixo. O primeiro conteúdo final correspondeu à amostra 76 em T1 e 45 em T2. Os relógios do servidor medem prefill e decode, os do cliente medem primeiro final e validação. O encerramento e as transições de porto estão contabilizados à parte.

Os três primeiros braços carregaram o mesmo ELF comum. FILTER e FIXED diferem pelo veto sobre o token anterior, SERIAL corre sem propostas. R reabre o layout GGUF numa biblioteca independente. A troca entre R e FILTER inclui o pack e o backend. O melhor decode nominal obtido nos pares de ordem inversa do pack continua em 5,361 e 5,263 tok/s. A parte 185 mediu também o C291 independente com pack. [Pares do pack](../../../../../../../../../../../../packed_nvme_manifest/server_profile/conversation/ordens.md) · [Quarta receita independente da família 185](../family.md)

## O que custaram as cinco verificações em falta

| IDs já confirmados em T2 | Propostas aceites | IDs confirmados pelo despacho | Filtro (ms) | Serial nas mesmas posições (ms) |
|---:|---:|---:|---:|---:|
| 11 | 1 | 2 | 575,296 | 464,309 |
| 16 | 2 | 3 | 520,510 | 615,225 |
| 19 | 2 | 3 | 467,134 | 555,997 |
| 37 | 1 | 2 | 339,187 | 279,135 |
| 41 | 1 | 2 | 448,514 | 352,465 |

Estes cinco grupos duraram **2,350641 s** no relógio do seu produtor, todos antes do primeiro final. Ao comparar com as duas projeções anteriores, os restantes intervalos mudaram o preço agregado em −0,310401 e −0,340748 s. O total de grupos novos mais resíduo foi 2,040240 e 2,009893 s para orçamentos de 0,858059 e 0,827712 s. Em ambos faltaram **1,182181 s de decode** para 47 saídas a 6 tok/s. O resíduo inclui mudanças de execução, de residência e de amostragem dos tempos entre processos. A contribuição causal de cada uma permanece desconhecida. Em T1 os sete novos grupos duraram 4,201786 s. [Projeção publicada antes do ensaio](../context.md)

No conjunto de todos os grupos de T2, os três com duas aceitações ganharam 286,861 ms contra o serial nas mesmas posições. Os três com uma aceitação perderam 267,088 ms e a rejeição imediata perdeu 308,191 ms. Os 30 intervalos sem proposta ganharam 88,328 ms. Estes grupos particionam exatamente as 46 transições nativas. A diferença entre esse intervalo e o decode do FILTER foi −12 µs. O sinal em grupos completamente aceites permite investigar uma composição parcial. Escolher simultaneamente grupos que cobrem as mesmas posições exigiria pagar o token repetido ou descartá-lo.

## Proveniência, recursos e limites

Medição no commit `59a12bfab5972e829c4a5bc55a8059cbe27727d0`, base integrada `293f5b184da9439771cce361cd33fc4068d749f4`. O servidor tem SHA-256 `054e983528d35731e2dc6222f1418f2f08120ef83e0c5f2a8db11805dd38effa`, o ELF comum do filtro `c4644477420b8d41d46db8d26291a4c4604afb70aa5c7dd415a3aa3412717914` e o GGUF `582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d`. Os inputs autenticam o pack, os pins C269/C291, comandos, providers numéricos, launcher, armazenamento Btrfs no NVMe e recursos. No Ryzen AI 9 HX 370 e RTX 4060 Laptop, driver 620.73.04, a janela C55 teve 62 amostras em 61,010 s, seguida por quatro C118 de 61 amostras. A família durou 840,300 s dos 2 700 s admitidos. Atingiu 14,740 GiB no cgroup sob E20, 6 854 MiB de VRAM e zero swap. Máximos de 83,5 °C na CPU, 57,89 °C na GPU e 51,85 °C no NVMe. A energia estimada da GPU foi 1 421,7 / 1 449,7 / 1 419,2 / 1 484,7 J, na ordem da tabela. Energia total do portátil desconhecida. Do sinal ao encerramento confirmado passaram 1 309 / 1 161 / 965 / 760 ms.

Cada processo terminou com código zero, identidade de dono verificada e porto livre. A primeira tentativa falhou no nome de unidade, antes dos pesos e de qualquer pedido. Guarda-se o FAIL e a correção que levou a verificação de identidade à preparação sem modelo. Os cinco pontos novos têm igualdade dos IDs gerados e das decisões do proposer. A igualdade bitwise dos logits completos e do KV foi qualificada no primeiro bloco natural da parte 182 e no controlo serial da parte 183. Nos cinco novos pontos fica por medir. Cenário de código, pares trace-OFF do avaliador e sessão sustentada desta receita ficam NOT_RUN. [Falha preservada](http-r02.md) · [Gate numérico](../../README.md)

A parte 193 guarda 184 ficheiros privados e 6 947 605 bytes, incluindo as preparações de R01/R02, a falha e os oito pedidos. A revisão dos originais e a do arquivo produziram exatamente `969326ae832d6a968981f5931a08d437e29ecdbcba6ed94a7a63887358266dd0`. O destino de cada revisão deve ser novo. [Manifesto do arquivo](../../../../../../../../../../../../private_archive/part-193.json) · [Revisor](review_http.py)

```sh
python3 -IB "$STUDY/review_http.py" \
  --failed "$AR/part-193/tesy-c281-context-http-20261126-r01" \
  --prepared "$AR/part-193/tesy-c281-context-http-prepared-20261126-r02" \
  --family "$AR/part-193/tesy-c281-context-http-20261126-r02" \
  --family-sha256 9fd6dadd86e88b9eea28c56b0b1ad43c782ba83634b6de6ecc502750915c34e1 \
  --capture "$AR/part-29/tesy-natural-ids-capture-20261125-r01" \
  --verified "$AR/part-29/tesy-natural-ids-verified-20261125-r01" \
  --plan "$AR/part-177/tesy-packed-causal-plan-20261126-r03" \
  --lookup-run "$AR/part-192/tesy-c281-native-context-20261126-r02" \
  --new-output-dir "$NEW"
```
