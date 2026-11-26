# A publicação do pack pelo manager C291

**GO para a fixture de uma camada CPU real.** No manager C291, escrever por `pread` diretamente na geração reservada eliminou 123 chamadas SET e 541 987 200 B de cópias de pesos por braço positivo. A ablação com o mesmo banco estriado, staging e três SET por falta reproduziu os mesmos pesos, gerações e contadores de publicação do controlo independente. O destino direto reproduziu-os também. Os quatro braços positivos leram os mesmos 542 097 408 B no leitor. O ganho de tempo no pedido permanece desconhecido. M3 continua PARTIAL e M4 NOT_MET. [Protocolo](protocol.md) · [Candidato R01](receipts/candidate-r01.json) · [Controlo R03](receipts/original-r03.json) · [Grafo misto](../packed_cpu_mixed/README.md)

| Fase em cada braço positivo | Leituras | Bytes pedidos e devolvidos por pread | SET original DENSE | SET candidato DENSE | SET STAGED | SET DIRECT | Bytes copiados em cada braço com staging |
|---|---:|---:|---:|---:|---:|---:|---:|
| Preenchimento das primeiras 36 slots | 36 | 475 987 968 | 108 | 108 | 108 | 0 | 475 891 200 |
| Quatro faltas simultâneas nas slots 36–39 | 4 | 52 887 552 | 12 | 12 | 12 | 0 | 52 876 800 |
| Repetição das quatro residentes | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Substituição na slot 0, geração 2 | 1 | 13 221 888 | 3 | 3 | 3 | 0 | 13 219 200 |
| **Total** | **41** | **542 097 408** | **123** | **123** | **123** | **0** | **541 987 200** |

Nos quatro braços, 12 chamadas ao remap registaram sete hits, 41 misses e 41 cargas publicadas. Quatro workers distintos reclamaram as quatro faltas simultâneas. Durante a pausa nas leituras o seletor de vítimas rejeitou as slots LOADING reclamadas. Nas cinco admissões acompanhadas individualmente, o destino do pread estava no staging em DENSE e STAGED e coincidia com a base da slot do respetivo claim em DIRECT. A fila drenou e o destrutor regressou. Os digests independentes das três projeções foram verificados nas 40 slots antes e depois da substituição, 240 verificações por braço positivo. A identidade comum dos estados e dos contadores foi `96751b1db3458e7fa4848d266f1726e2340c2936a99d48b36ef5ea3e19da7bf4`. Cada positivo somou 79 552 512 B da leitura de prova do pack e 1 057 536 000 B percorridos em RAM nos dois snapshots, contabilizados separadamente do serviço. [Validação](VALIDACAO.md) · [Verificador](run.py)

| Falha injetada | Modos do mesmo executável candidato | Retorno do syscall / retorno entregue ao leitor (B) | SET DENSE / STAGED / DIRECT | Publicações |
|---|---|---:|---:|---:|
| `short` | DENSE, STAGED, DIRECT | 13 217 792 / 13 217 792 | 0 / 0 / 0 | 0 |
| `short_tail` | STAGED, DIRECT | 13 221 888 / 13 219 200 | fora do protocolo / 0 / 0 | 0 |
| `shutdown` com leitura em voo | DENSE, STAGED, DIRECT | 13 221 888 / 13 221 888 | 3 / 3 / 0 | 0 |

Nos oito negativos, a geração 1 da slot 0 terminou em LOADING, com o claim libertado e zero cargas comprometidas. Os retornos curtos ativaram o erro persistente do manager. No encerramento o sinal de shutdown estava ativo, a fila vazia e o erro persistente desligado. DENSE e STAGED chegaram a copiar 13 219 200 B antes de o manager recusar a publicação no shutdown. Em `short_tail`, a fixture injetou o retorno reduzido **depois de um syscall completo** para testar a fronteira que aceita ou rejeita a janela. Cada braço usou um processo novo e confirmou o retorno do destrutor. [Fixture e controlo de falhas](fixture.cpp) · [Onze braços individuais](receipts/candidate-r01.json)

| Identidade | Resultado | Workers observados | Parede da tentativa | Pico de memória do cgroup |
|---|---|---:|---:|---:|
| [R01](receipts/original-r01.json) | FAIL preservado no precheck. A checkout sparse omitiu o leitor do estado do cgroup. | 0 | 0,033 s | Sem amostra |
| [R02](receipts/original-r02.json) | FAIL preservado no precheck dos ELF, depois da compilação. A regra encontrou “cuda” no nome do diretório de build. Entre as bibliotecas GGML, o carregador resolveu apenas `libggml-base.so.0`. | 0 | 4,789 s | 527 962 112 B até ao último comando observado |
| [R03](receipts/original-r03.json) | PASS do original com a verificação da biblioteca resolvida corrigida. | 4 | 5,473 s | 703 647 744 B |
| [Candidato R01](receipts/candidate-r01.json) | PASS dos três positivos e dos oito negativos. | 4 por processo | 7,986 s | 705 261 568 B |

No R03 original o build demorou 4,300 s e o braço nativo 0,719 s, com 594 456 KiB de RSS máximo. No R01 candidato o build demorou 4,477 s. O maior RSS dos braços foi 594 876 KiB. A parede ativa combinada foi 13,460 s. Os cgroups positivos terminaram com zero swap e sem eventos de limite máximo ou OOM. O pack de seis registos ocupou 79 552 512 B no Btrfs/NVMe e a sua limpeza foi confirmada. O orçamento foi 1 GiB de memória, zero swap, até 180 s por processo e 720 s de parede para a família. Os tempos incluem sincronização e verificação e qualificam o custo do ensaio. Zero forwards e zero utilização da GPU na fixture do manager. [Recibo R01](receipts/candidate-r01.json)

A fonte independente é C291 `c89c88b342054223e3f27a17fbfd0954803147ac`, árvore `3962daa588dfa89971c60c95ce4c5054bc27fd3f`. R01 e R02 originais usaram o supervisor `a5d98e99a15ff84cf8d6f90addbb0d988d76f9c4`. R03 passou em `d71985694ec8bd3cd476e673522cd09e821d301e`, árvore `9b05a81510410a29e5b079f92c86f0a09c86c7dc`. O candidato foi medido em `df64d07caea8033ee01d856fddfd7f6b9ef2a2ff`, árvore `236b158ff82d66d023b586694fbb07205a8f6e5c`, patch SHA-256 `636a88a0ec71a4fc78608145e884a06132c67f45c9f23f56a9fca135f9f47684`. Os recibos privados completos têm SHA-256 `c1904073c2b6641ccff5bf2f5230f04fd9ddeb59babf8b55461285ac19a26535` e `3e5e58c234e46311be3512f2701ff2483fb5153c17e3b71e866d3c1086db5023`, respetivamente. [Patch](arena.patch) · [Instruções de reprodução](VALIDACAO.md)

A unidade cobre um índice de teste de uma camada com 36 experts a partilhar um registo de zeros e cinco registos seguintes distintos. Os endereços e digests provam a passagem dos pesos pelo manager nestes braços. A próxima fixture deve confrontar a camada CPU0 real com uma referência independente, preservando router, top-k, projeções, ativação e redução. A validação do índice integral de 4 608 experts, as fronteiras de logits e o tempo da conversa continuam abertos. [Fonte C291](../../../patches/c291-integral-expert-store.patch) · [Arquivo privado](../private_archive/README.md)
