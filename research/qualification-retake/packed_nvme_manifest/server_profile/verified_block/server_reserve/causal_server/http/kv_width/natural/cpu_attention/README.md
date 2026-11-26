# A atenção CPU de uma e três consultas com histórico longo

**GO para testar o mesmo cálculo no grafo natural do 120B.** No Ryzen, a redução da atenção serial muda quando o KV físico chega a 512 células. A fixture carregou os mesmos ELF CPU e base GGML que o processo natural. Com a janela de 128 e 2 304 células, o operador de três consultas diferiu do serial em 12 287 das 12 288 saídas. Aplicar o operador de uma consulta a três vistas do mesmo bloco recuperou as 12 288 palavras. As duas execuções independentes produziram ficheiros idênticos nos seis casos. [Pré-registo](protocol.md) · [Contagens por posição](result.json)

| Células | Posição inicial | BLOCK vs SERIAL com máscara completa | BLOCK vs SERIAL com janela de 128 | ROWS vs SERIAL, cada máscara |
|---:|---:|---:|---:|---:|
| 256 | 189 | 0 | 0 | 0 |
| 512 | 382 | 12 288 | 12 288 | 0 |
| 2 304 | 2 062 | 12 288 | 12 287 | 0 |

Cada contagem cobre três saídas de 4 096 F32 finitos. Os seis casos totalizam 73 728 palavras coincidentes com a referência para ROWS em cada processo. Trocar a primeira e a última máscaras alterou as 4 096 palavras de ambas as linhas e preservou a central em todos os casos. A fixture tem operandos gerados, usa os sinks, os tipos e as strides do grafo e fornece caudas diferentes nas células invisíveis. As oito threads e os oito providers foram fixados. O limite de memória foi 2 GiB por processo, picos de 20 865 024 e 21 876 736 B, zero swap. Os dois processos com criação e encerramento das unidades demoraram 0,151 e 0,143 s. O modelo e a GPU ficaram fora da fixture. A energia do anfitrião é desconhecida.

A camada 0 é CPU/SWA neste modelo. Os logits e o KV do bloco real da parte 180 só discriminam o percurso até às projeções de KV de L1. A nova fixture mostra que é possível explicar uma divergência no operador com dados controlados. Para atribuir o resultado no modelo é preciso aplicar a mudança com o ELF, máscaras, propostas, pool e trabalho idênticos, reproduzir o contraexemplo com a mudança desligada e confrontar todo o estado com P. [Resultado original no target](../README.md)

A revisão sem modelo nos originais e na parte 181 deu o mesmo SHA-256 `83377c233f87f975e94fdd5a2111ab36e0e58b5bdbf170ec41a87b62b9e12401`. A parte 181 tem 68 ficheiros privados e 2 459 263 B. [Build](build.py) · [Supervisor](run.py) · [Revisor](review.py) · [Manifesto](../../../../../../../../../private_archive/part-181.json)
