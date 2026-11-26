# Capacidade da L2 à entrada do decode

**NO_GO nos quatro braços C294 para obter seis passos/s apenas por retenção de experts em RAM, com o serviço e as dependências de C295.** Mesmo com conhecimento do futuro, 378 entradas escolhidas entre quaisquer experts, repetições gratuitas e serviço a 80% da duração original, os dois braços nominais precisam de 5,437 e 5,506 s. Os de código precisam de 6,752 e 6,794 s. O orçamento comum para os 32 passos fornecidos é 5,333333 s. Cada braço falha individualmente, incluindo com 243 entradas. O NO_GO abrange este regime de serviço. M3 continua PARTIAL e M4 NOT_MET. [Protocolo](protocol.md) · [Recibo completo](evidence/receipt.json)

## Tempos dos quatro braços

Cada célula dá os segundos de decode nas escalas **0,8 / 1,0 / 1,2**. «Livre» concede qualquer identidade inicial. «Prefixo» admite as rotas efetivas do prefixo e as publicações do incremento. Nos quatro braços o bitmap de reservas dá os mesmos tempos que os ranks do prefixo. Os universos do prefixo contêm 2 659 chaves no nominal e 2 476 em código, comparadas com as 4 608 concedidas no livre. As durações são SIMULADAS. A janela original contém 1 081 leituras de decode por braço nominal e 1 308 por braço de código.

| Braço C294 | K | Livre, mínimo otimista (s) | Livre, testemunho finito (s) | Prefixo, testemunho finito (s) |
|---|---:|---:|---:|---:|
| nominal153, 2 | 0 | 7,763 / 9,260 / 10,758 | 7,832 / 9,346 / 10,861 | 7,832 / 9,346 / 10,861 |
| nominal153, 2 | 243 | 6,178 / 7,279 / 8,380 | 6,178 / 7,279 / 8,380 | 6,248 / 7,367 / 8,486 |
| nominal153, 2 | 378 | 5,437 / 6,353 / 7,269 | 5,437 / 6,353 / 7,269 | 5,540 / 6,482 / 7,423 |
| nominal153, 3 | 0 | 7,802 / 9,294 / 10,787 | 7,873 / 9,384 / 10,895 | 7,873 / 9,384 / 10,895 |
| nominal153, 3 | 243 | 6,244 / 7,348 / 8,451 | 6,244 / 7,348 / 8,451 | 6,307 / 7,426 / 8,546 |
| nominal153, 3 | 378 | 5,506 / 6,425 / 7,344 | 5,506 / 6,425 / 7,344 | 5,601 / 6,544 / 7,486 |
| code153, 2 | 0 | 9,069 / 10,881 / 12,694 | 9,122 / 10,948 / 12,774 | 9,122 / 10,948 / 12,774 |
| code153, 2 | 243 | 7,496 / 8,915 / 10,335 | 7,496 / 8,915 / 10,335 | 7,545 / 8,977 / 10,409 |
| code153, 2 | 378 | 6,752 / 7,986 / 9,219 | 6,752 / 7,986 / 9,219 | 6,821 / 8,072 / 9,323 |
| code153, 3 | 0 | 9,089 / 10,904 / 12,719 | 9,146 / 10,975 / 12,804 | 9,146 / 10,975 / 12,804 |
| code153, 3 | 243 | 7,541 / 8,969 / 10,397 | 7,541 / 8,969 / 10,397 | 7,578 / 9,016 / 10,453 |
| code153, 3 | 378 | 6,794 / 8,035 / 9,276 | 6,794 / 8,035 / 9,276 | 6,848 / 8,103 / 9,357 |

Com 243 e 378 entradas, os testemunhos ótimos cabem em todos os instantes nos três universos e atingem o respetivo mínimo. Continuam a escolher chaves com informação futura. Com K=0 o oráculo concede as repetições nascidas durante o decode, sendo 32 no nominal e 23 em código. O testemunho de capacidade zero tem zero hits e reproduz o controlo C295. A comparação com a triagem anterior confere que iniciar com K entradas em P e passar a capacidade ilimitada após P é uma concessão mais favorável. [Limite anterior em P](../l2_warm_critical/README.md) · [Intervalos de residência](solver.py) · [Confirmação pelo simulador](screen.py)

## Materialização e tempo admissível

Cada triplo contém 13 219 200 B de pesos originais. As colunas de origem contam **cópias integrais** no prefixo até P, no incremento P→I e em P10 durante o decode. Cada hit exige ainda outra cópia integral da L2 para o staging do worker. Nas agendas concretas, a quantidade total de bytes dessa segunda cópia é igual à da primeira. As entregas para o primário (CPU ou CUDA) continuam integrais. O caso livre concede uma origem anterior a P até a chaves sem produtor demonstrado. A tabela cobra o payload dessa hipótese. O recibo desagrega cada custo por fase e dispositivo.

| Braço | K | Fontes demonstradas, cópias P / incremento / decode | Livres, cópias P / incremento / decode | GiB por sentido de cópia | Melhor excesso sobre 5,333333 s com fontes demonstradas / livres, escala 0,8 |
|---|---:|---:|---:|---:|---:|
| nominal153, 2 | 243 | 145 / 98 / 32 | 171 / 72 / 32 | 3,386 | 0,915 / 0,844 s |
| nominal153, 2 | 378 | 234 / 144 / 32 | 276 / 102 / 32 | 5,048 | 0,207 / 0,104 s |
| nominal153, 3 | 243 | 144 / 99 / 32 | 172 / 71 / 32 | 3,386 | 0,974 / 0,911 s |
| nominal153, 3 | 378 | 232 / 146 / 32 | 277 / 101 / 32 | 5,048 | 0,268 / 0,173 s |
| code153, 2 | 243 | 76 / 167 / 23 | 110 / 133 / 23 | 3,275 | 2,212 / 2,162 s |
| code153, 2 | 378 | 117 / 261 / 23 | 170 / 208 / 23 | 4,937 | 1,488 / 1,419 s |
| code153, 3 | 243 | 76 / 167 / 23 | 114 / 129 / 23 | 3,275 | 2,245 / 2,207 s |
| code153, 3 | 378 | 120 / 258 / 23 | 175 / 203 / 23 | 4,937 | 1,515 / 1,460 s |

A margem para custos positivos de retenção, coordenação e cópias adicionais é **zero em todas as escalas** para todas as origens. O custo de tempo por origem continua desconhecido. Os contrafactuais acima já falham quando se concede tempo zero a essas operações. O fim F fica sem entradas L2 retidas. RAM, NVMe e H2D reais e durações de pedidos naturais exigem os seus próprios ensaios.

## Condição quantitativa para reabrir

Para K=378 na variante livre, seja F a duração fixa de trabalho fora do serviço e S a soma dos máximos de serviço de cada barreira após os hits. A linha confirmada pelo C295 é **T(s) = F + s × S**. Mantendo o mesmo trabalho, cópias adicionais gratuitas e as mesmas dependências, a maior escala admissível é **s = (32/6 − F) / S**, com F e S em segundos. As quatro escalas necessárias ficam abaixo de 0,8. A escala representa a fração residual do serviço READ + cópia + overhead que resta nas barreiras C295. A sua alteração exigiria mecanismo e nova evidência. A taxa física de NVMe permanece por medir.

| Braço, K=378 livre | F (s) | S (s) | Maior escala admissível |
|---|---:|---:|---:|
| nominal153, 2 | 1,773408 | 4,579962 | 0,777283 |
| nominal153, 3 | 1,830919 | 4,594404 | 0,762322 |
| code153, 2 | 1,817114 | 6,168620 | 0,570017 |
| code153, 3 | 1,829011 | 6,205900 | 0,564676 |

## Reprodução

O avaliador autentica a família WRT1/TPR1, as publicações dos quatro C294, os estados P/I/F e os controlos C295. Cada identidade de hit volta ao grupo e à geração nativa do seu P5. Ambos os cenários dos 1 152 grupos por braço foram conferidos no simulador às três escalas. As saídas são privadas e exclusivas por tentativa.

```sh
python3 -B research/qualification-retake/l2_decode_entry/screen.py \
  --family "$WRT_FAMILY" --raw-dir "$TESY_C294_RAW" --new-output-dir "$DESTINO_NOVO"
```

As confirmações r01 e r02 usaram o commit `55e8a48c4e7458c7902e957ff3ac5140c34fcfa5` e a árvore limpa `a1603c85d4311801f2857b3cd8ed0a9e658cc327`. Correram em CPU com zero forwards, pesos ou GPU. A r01 levou 3,13 s e 109 480 KiB de RSS máxima. A r02 levou 3,16 s e 109 776 KiB. Os dois recibos originais e o publicado têm 369 069 B e SHA-256 `3f1f4c2760554a1f8b074dde4309da23a5bf7cbd5a3029586f0d48bb6679b6dd`. O JSON compacto conserva listas, valores e precisão. Para verificar igualdade semântica com outra cópia íntegra, usar o comando abaixo. [Recibo](evidence/receipt.json)

```sh
python3 -c 'import json,sys; a,b=map(open,sys.argv[1:]); assert json.load(a)==json.load(b)' \
  research/qualification-retake/l2_decode_entry/evidence/receipt.json "$DESTINO_NOVO/receipt.json"
```
