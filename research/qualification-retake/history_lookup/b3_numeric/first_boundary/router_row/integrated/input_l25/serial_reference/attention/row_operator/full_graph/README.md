# O grafo recuperou a atenção, a projeção e o router de L25

**MEDIDO e REPRODUZIDO.** No 120B original, inserir as três vistas apenas na atenção CUDA da camada 25 restaurou os 12 288 F32 na saída da atenção, os 8 640 após a projeção e todos os logits, IDs top-4 e pesos do router dessa camada. A primeira diferença observável avançou para a saída dos experts da própria L25. Das 2 880 palavras de cada posição, diferem agora 33, 29 e 109 face ao target serial. O prefixo inteiro e a entrada do bloco passaram. **GO para conservar a correção local. NO_GO para promover este B3 como verificador exato.** [Resultados por posição e por braço](result.json) · [Protocolo anterior à execução](protocol.md)

| Contrato face a AR | OFF | ON, atenção por linha em L25 |
|---|---:|---:|
| Primeiro corte diferente, posições 189 / 190 / 191 | Atenção antes da projeção, 4 096 / 4 096 / 4 096 F32 | Saída FFN de L25, 33 / 29 / 109 F32 |
| Payloads de ativação iguais, de 1 185 | 1 071 | 1 090 |
| Primeira camada com KV F16 diferente | 26 | 27 |
| Palavras de KV pós-bloco diferentes, de 5 898 240 | 29 809 | 26 887 |
| Quadruplos top-4 ordenados diferentes, de 108 | 0 | 2 |
| Logits completos bit a bit iguais, de 5 | 1 | 1 |
| Argmax únicos iguais, de 5 | 5 | 5 |

O único vetor de logits inteiramente igual foi o último do prefill. Nos quatro vetores seguintes ON alterou 201 088, 201 088, 201 088 e 201 087 dos 201 088 F32 respetivos. Na posição 191 em L29, três dos quatro experts são comuns. Em L30 os mesmos quatro experts aparecem com duas posições trocadas. Estas diferenças impedem adotar os tokens do candidato. O agrupamento dos dados em B3 pode mudar o resultado do próprio cálculo do target. A distribuição de sampling permanece por qualificar.

OFF reproduziu integralmente o B3 contemporâneo da parte 165. Ambos os processos usaram o mesmo driver, ELF e DSO, `TESY_B3_ROUTER_ROW=1`, os mesmos 189+3+1 IDs, máscaras e estado inicial. Só a opção da atenção em L25 mudou. A primeira compilação terminou antes de produzir a biblioteca por um campo inexistente no pin. A compilação seguinte usou o campo `attn_soft_cap`, verificou os 171 inputs de link e reutilizou 165 objetos. R0 slots40-persistent continua a ser o controlo operacional. [Origem do grafo privado](materialize.py) · [Revisor independente sem GPU](review.py)

| Recursos no portátil | OFF | ON |
|---|---:|---:|
| Processo com observador / scope com C118 | 28,449 / 89,518 s | 28,207 / 88,970 s |
| VRAM máxima / swap | 6 868 MiB / 0 | 6 868 MiB / 0 |
| Pico de cgroup | 15 869 931 520 B | 15 954 542 592 B |
| Inventário C118 / observações do mapa nativo | 61 / 108 | 61 / 109 |
| Energia GPU estimada e cobertura | 333,2 J em 27,744 s | 327,3 J em 27,534 s |

Os dois scopes terminaram, com zero pedidos HTTP. Os máximos foram 73,25 °C CPU, 52,79 °C GPU e 47,85 °C NVMe. A energia do portátil e a latência de conversa desta intervenção continuam desconhecidas. A campanha está em `7ac1bad9`, com protocolo em `0173d6ae`. O revisor dos originais e o da parte 167 produziram o mesmo SHA-256 `0f2752da2a91444343ed5165c442b75e62d583dfd95084da750b38149afe3114`. [Manifesto privado](../../../../../../../../../../private_archive/part-167.json)

A próxima comparação deve isolar a FFN CUDA de L25 com os três operandos normalizados, os pesos de mistura, as rotas e os bytes dos experts efetivamente usados. Uma alternativa ao desvio no produto dos experts é uma diferença posterior em SwiGLU, ponderação ou soma dos ranks. O novo resultado desloca a investigação para essa cadeia. O melhor turno de produto emparelhado mantém 18,313 s até ao primeiro conteúdo final e 5,361 tok/s. M3 PARTIAL, M4 NOT_MET.
