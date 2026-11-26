# Banco exclusivo de vítimas durante T2

**O banco exclusivo poupa 83 leituras no prefill, mas acrescenta 25 no decode.** A promoção retira o expert do banco e liberta a entrada para uma vítima do primário. Na conversa nominal ON R02, o prefill passa de 1 058 para 975 leituras e o decode de 797 para 822. Mesmo com custo temporal zero para 198 leituras novas de decode, para os SET sem preço e para as cópias das vítimas, o primeiro conteúdo final ainda excede 10 s em **156–191 ms** na agenda serial a 4,5 GB/s. A variante falha os dois critérios de progressão pré-registados. [Protocolo](protocol.md) · [Recibo agregado](evidence/receipt.json)

O antecedente de vítimas LRU mantinha a entrada secundária após o hit. Já a ablação emparelhada nesta conversa preservava as 353 chaves de T1 durante todo o pedido. Este ensaio manteve nos dois braços os mesmos tags de prioridade primária selados antes de T2, os 40 slots por camada e o estado de calor e recência. A disponibilidade dos bytes mudou. A igualdade das reservas e das filas lógicas permitiu comparar as origens em cada sítio do alvo; o replay confirmou também as 2 354 reservas históricas de R0. [Antecedente de LRU em T2](../../../../t2_victims/protocol.md) · [Antecedente com banco aquecido em T1](../../../../t1_victims/protocol.md) · [Ablação na mesma captura](../replay/README.md)

| Fase | READ de disco, banco fixo | READ de disco, banco exclusivo | Hits de RAM no exclusivo | READ eliminados / introduzidos |
|---|---:|---:|---:|---:|
| 5 tokens | 34 | 34 | 25 | 0 / 0 |
| 148 tokens | 1 024 | 941 | 284 | 201 / 118 |
| Prefill completo | 1 058 | 975 | 309 | 201 / 118 |
| Decode, 46 avaliações | 797 | 822 | 374 | 173 / 198 |

Dos 353 registos à entrada, 48 já tinham cópia no primário e foram removidos do banco exclusivo, sem recuar no histórico para os substituir. O banco começou com 305 chaves, atingiu 339 no primeiro retorno e chegou ao decode cheio. No prefill descartou 927 vítimas LRU por falta de capacidade e no decode descartou 822. As identidades dependem da ordem das reservas, da entrada efetivamente capturada e das rotas do pedido.

## Bytes que a troca exige

Cada admissão nestas duas fases substitui um ocupante. Assim, por coincidência da ocupação desta trajetória, os bytes de captura primário→banco igualam os de entrega ao primário. São movimentos distintos. Um hit usa também um scratch que permite libertar a entrada sem perder os bytes a entregar. Os SET da última coluna já incluem a entrega de hits vindos desse scratch e a entrega de faltas vindas do disco.

| Fase e tier | Leituras de disco fixo → exclusivo | Primário → banco (B) | Banco → scratch (B) | Entregas SET ao primário (B) |
|---|---:|---:|---:|---:|
| 5, CPU | 26 → 26 | 634 521 600 | 290 822 400 | 634 521 600 |
| 5, CUDA | 8 → 8 | 145 411 200 | 39 657 600 | 145 411 200 |
| 148, CPU | 635 → 602 | 10 178 784 000 | 2 220 825 600 | 10 178 784 000 |
| 148, CUDA | 389 → 339 | 6 014 736 000 | 1 533 427 200 | 6 014 736 000 |
| Decode, CPU | 541 → 577 | 11 513 923 200 | 3 886 444 800 | 11 513 923 200 |
| Decode, CUDA | 256 → 245 | 4 296 240 000 | 1 057 536 000 | 4 296 240 000 |

Os 975 registos de prefill correspondem a 12 888 720 000 B úteis e 12 891 340 800 B alinhados no pack. Em T2, a captura de vítimas do consumidor CUDA soma 10 456 387 200 B de retorno a RAM. Os dois braços compartilham a mesma preparação anterior ao POST. No sufixo T1 observado, essa preparação custa de 16 814 822 400 a 20 225 376 000 B de origem CPU e de 6 847 545 600 a 8 103 369 600 B de origem CUDA, conforme o conteúdo inicial. O handoff conservador requer mais um scratch lógico de 13 219 200 B para uma transação de cada vez.

## Relógios e decisão

| Cenário condicional, com custos desconhecidos a zero | Ordem RP | Ordem PR |
|---|---:|---:|
| Piso de decode a preços de READ do pack e SET comuns | 6,358854 s | 6,394350 s |
| Teto com 47 saídas / 46 avaliações, por segundo | 7,391 / 7,234 | 7,350 / 7,194 |
| Margem de decode para 6 tok/s, 47 saídas | +1,474479 s | +1,438984 s |
| Lacuna máxima do prefill a 4,5 GB/s | 0,995341 s | 0,959845 s |
| Margem até 10 s com a agenda serial | **−0,155810 s** | **−0,191306 s** |
| Banda mínima do prefill com a agenda serial | 4,759 GB/s | 4,822 GB/s |
| Margem após esconder todas as lacunas elegíveis do pipeline | +0,635856 s | +0,600361 s |

Somente 624 das leituras de decode continuam no mesmo sítio do plano físico. O cálculo conserva o exterior observado de R0 (2,318241 s), cobra essas leituras e os 969 SET com correspondência, combinados na maior cadeia de cada uma das 1 656 callbacks. Dá custo zero às 198 leituras novas e aos 227 SET sem preço. A aparente redução do piso temporal mesmo com mais jobs de disco decorre, em parte, deste conjunto maior de trabalho sem medida. Não estabelece uma aceleração do decode. No prefill, a agenda serial conserva 1,151151 s de lacunas medidas e o pipeline otimista conserva 0,359485 s. A margem de 600–636 ms na combinação teria de pagar **todos** os custos críticos omitidos, inclusive as dependências, promoção, cópias, sincronização e os READ novos. [Fronteira de prefill](../prefill_frontier/README.md) · [Proveniência dos preços físicos por job](../replay/decode_clock/transport/service-result.md)

A política decide a troca em ordem de reserva e exige posse dos bytes antes de reutilizar cada entrada. A ordem de PUBLISH dos workers não decide a posição na LRU. Uma implementação assíncrona teria de demonstrar a mesma posse sob concorrência e respeitar o último consumidor CUDA e as gerações; atualizar a LRU na conclusão de DMA poderia mudar as decisões. O replay comprova a contabilidade desse contrato lógico. Nenhuma cópia, corrida de GPU ou mudança do launcher foi executada.

## Reprodução

Pré-registo `cd99ce60`, programa `45a77f9c`, quatro testes portáveis. R01 e R02 em checkout limpa custaram 0,69 s de parede cada, com RSS máxima de 74 316 e 74 344 KiB. Os recibos são byte a byte idênticos (12 361 B), SHA-256 `c6179e94dad63b913fb238c05e74adc272acddd2482d546c42e3da035023bef9`. A análise usa as partes seladas 63, 65 e 66. A parte 69 arquiva os dois planos físicos e as duas confirmações deste replay, num total de 6 ficheiros e 3 482 554 B. O manifesto tem SHA-256 `019d46de75a0742e1704001aed05b124c37eb53151a8083413b3b2cb8ab3a89d`. [Programa](screen.py) · [Testes](test_screen.py)

```sh
DIR=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/exclusive_bank
OPENBLAS_NUM_THREADS=1 python3 -IB "$DIR/test_screen.py"
OPENBLAS_NUM_THREADS=1 python3 -IB "$DIR/screen.py" \
  --archive "$ARCHIVE" --new-output-dir "$NEW"
sha256sum "$NEW/receipt.json"
```
