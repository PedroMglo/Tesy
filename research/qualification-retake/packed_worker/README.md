# A publicação do pack pelo manager C291

**PASS do controlo original DENSE.** Os quatro workers reais do C291 serviram a camada CPU sintética. A repetição com quatro hits dispensou leituras e SET. Na substituição do primeiro residente, a segunda geração entregou os três componentes previstos pelo gold independente. O candidato com banco estriado e destino direto continua **NOT_RUN** nesta unidade. A comparação depende da qualificação do grafo misto, da revisão de `arena.patch` e dos braços no mesmo executável candidato. [Pré-registo](protocol.md) · [Recibo R03](receipts/original-r03.json) · [Grafo misto](../packed_cpu_mixed/contract.md)

| Fase do original | Leituras completas | Bytes pedidos e devolvidos por pread | SET | Bytes copiados pelo SET |
|---|---:|---:|---:|---:|
| Primeiros 36 residentes | 36 | 475 987 968 | 108 | 475 891 200 |
| Quatro admissões finais nas slots 36–39 | 4 | 52 887 552 | 12 | 52 876 800 |
| Repetição residente | 0 | 0 | 0 | 0 |
| Substituição na slot 0, geração 2 | 1 | 13 221 888 | 3 | 13 219 200 |
| **Total** | **41** | **542 097 408** | **123** | **541 987 200** |

As 12 chamadas ao remap registaram sete hits, 41 misses e 41 publicações de cargas. Nas cinco admissões acompanhadas individualmente, o pread teve como destino o staging, fora da cache. Cada um dos quatro workers reclamou uma das quatro admissões simultâneas. Verificámos as gerações e os digests de gate/down/up nas 40 slots antes e depois da substituição, 240 projeções no total. O destrutor regressou depois do join. O custo da prova incluiu 79 552 512 B de leitura direta do pack inteiro e 1 057 536 000 B percorridos em RAM para os dois snapshots. Essas leituras de verificação são adicionais ao pread dos workers. Os bytes pedidos e copiados acima medem as APIs. O tráfego físico do NVMe e o tempo poupável no pedido permanecem desconhecidos. [Método de validação e reprodução](VALIDACAO.md)

| Identidade | Resultado | Workers observados | Parede da tentativa | Pico de memória do cgroup |
|---|---|---:|---:|---:|
| [R01](receipts/original-r01.json) | FAIL preservado no precheck. A checkout sparse omitiu o leitor do estado do cgroup. | 0 | 0,033 s | Sem amostra |
| [R02](receipts/original-r02.json) | FAIL preservado no precheck dos ELF, depois da compilação. A regra encontrou “cuda” no nome do diretório de build. Entre as bibliotecas GGML, o carregador resolveu apenas `libggml-base.so.0`. | 0 | 4,789 s | 527 962 112 B até ao último comando observado |
| [R03](receipts/original-r03.json) | PASS do original com a verificação da biblioteca resolvida corrigida. | 4 | 5,473 s | 703 647 744 B |

No R03 o build demorou 4,300 s. O braço nativo demorou 0,719 s e registou 594 456 KiB de RSS máximo. O cgroup terminou com zero swap e sem eventos de limite máximo ou OOM. O pack sintético de seis registos ocupou 79 552 512 B em Btrfs/NVMe. O supervisor confirmou a limpeza dos inputs que gerou após PASS. O ensaio usou um cgroup de 1 GiB, zero swap, até 180 s por processo e até 720 s por família. Os tempos incluem sincronização de workers e verificações de integridade. Zero forwards e zero utilização da GPU pelo ensaio. [Recibo de execução](receipts/original-r03.json)

A fonte independente é o C291 `c89c88b342054223e3f27a17fbfd0954803147ac`, árvore `3962daa588dfa89971c60c95ce4c5054bc27fd3f`. As duas primeiras tentativas usaram o supervisor `a5d98e99a15ff84cf8d6f90addbb0d988d76f9c4`. A confirmação decorreu em `d71985694ec8bd3cd476e673522cd09e821d301e`, árvore `9b05a81510410a29e5b079f92c86f0a09c86c7dc`. O SHA-256 do recibo original completo é `c1904073c2b6641ccff5bf2f5230f04fd9ddeb59babf8b55461285ac19a26535`. A alegação cobre a publicação pelo manager de uma camada com seis registos sintéticos. A segurança do candidato durante uma leitura pendente, a validação do índice integral, o consumo pelo FFN e o efeito em logits e no relógio do utilizador têm gates próprios. [Fonte C291](../../../patches/c291-integral-expert-store.patch) · [Instruções de reprodução](VALIDACAO.md)
