# Tempo entre camadas com serviço autorizado pelo router da própria camada

**NO_GO condicional, na parte 40.** As 793 admissões mínimas do banco de vítimas e os intervalos observados entre camadas consomem mais do que o orçamento do prefill nominal. A 4,5 GB/s de payload útil constante, as admissões de 10 482 825 600 B custariam 2,329517 s. Ao reservar 47/6 s para o decode, o tempo disponível para *todo* o restante trabalho serial de prefill é 46,107 ms. Só as 205 transições intercamadas drenadas ocuparam 1 142,612 ms no T2 deste pedido. Na melhor combinação do crivo poderia conservar-se até 4,04% desta duração. [Custo mínimo com 40 slots](../cuts.md) · [Protocolo](protocol.md) · [Recibo](receipt.json)

| Conversa e âmbito das 793 cargas | Denominador do decode | Orçamento de prefill (s) | Tempo disponível além da leitura (ms) | Fração máxima do tempo entre camadas | Banda útil requerida mantendo os intervalos (GB/s) |
|---|---:|---:|---:|---:|---:|
| Parte 40, banco do próprio T1 | 47/6 | 2,375624 | 46,107 | 4,04% | 8,502 |
| Parte 40, mesmo banco | 46/6 | 2,542290 | 212,774 | 18,62% | 7,489 |
| Parte 37, sensibilidade transferindo o volume | 47/6 | 2,430748 | 101,231 | 8,78% | 8,208 |
| Parte 37, mesma sensibilidade | 46/6 | 2,597415 | 267,898 | 23,22% | 7,260 |

O denominador principal conta os 47 tokens previstos. A variante de 46 conta avaliações autoregressivas depois do primeiro. Cada pedido conserva o seu próprio orçamento temporal. A parte 40 preserva o FAIL histórico de transporte de ordem e bindings entre sessões. Os limiares da primeira e da segunda linhas usam exclusivamente as autoridades dessa sessão. O banco de vítimas do T1 da parte 37 permanece desconhecido.

**REPRODUZIDO dos registos PFJ1.** Foram qualificadas 205 de 205 transições entre camadas consecutivas com rotas reais em cada pedido. Na parte 40 os intervalos duraram 144,236 ms na chamada de 5 e 213,719, 212,952, 219,095, 214,585 e 138,025 ms nas cinco tiles da chamada de 148. A parte 37 totalizou 1 153,584 ms. Em todos os casos, a última callback da camada anterior terminou com zero slots LOADING, claims e entradas na fila. Nenhum despacho, serviço ou publicação atravessou o intervalo até à callback que autoriza a próxima camada. Os relógios do host são monotónicos. A soma exclui transições entre tiles e chamadas. Dos 1 142,612 ms na parte 40, 1 085,109 ms sucederam a uma camada colocada na CPU e 57,502 ms a uma camada colocada na GPU. Essa classificação indica a origem da transição. A duração pode incluir cálculo, sincronização, transporte e o router seguinte. [Auditor de conservação e geometria](../../t1_manager_bank/decode_entry/compare.py) · [Definição e teste do intervalo](screen.py)

**FORMAL, com as premissas fixadas.** Para um orçamento de prefill P, B bytes de leitura, banda útil r e G segundos de intervalos drenados, a soma serial fica em B/r + fG quando se conserva a fração f. O limite de f é (P−B/r)/G. Para conservar G inteiro, a banda requerida é B/(P−G). A conta concede banco gratuito, zero custo dos SET, sem transferências duplicadas e reposição ótima das fronteiras obrigatórias dos dois retornos. Assume que cada leitura só pode ser autorizada pelo router da sua própria camada e que nenhum trabalho independente fica disponível durante G. São condições favoráveis para o volume, restritivas para a sobreposição.

**Origem e condição de reabertura.** No C269 `d0ebfbcc6c8f456bc1083027c1b08075a32824d8`, `src/models/openai-moe.cpp:77–153` faz depender cada nova atenção e FFN da saída residual anterior. `src/llama-graph.cpp:1964–1997,2171–2186` constrói as callbacks que recebem os IDs reais e a dependência entre waves. `src/llama-moe-stream.cpp:578–702,785–816` usa os IDs de w0 na camada atual e admite preloads da sua próxima wave. O recibo autentica os três blobs do pin. Em arquitetura alternativa, uma leitura especulativa anterior, um trabalho já autorizado mantido em staging entre camadas ou a antecipação do ponto onde o router publica os IDs podem sobrepor I/O a estes intervalos. Tal política precisa de provar chaves, causalidade, vida das gerações, bytes desperdiçados, trabalho concorrente e exatidão. Os intervalos medidos também podem encurtar se o grafo ou o serviço mudarem. O crivo não mede a taxa útil física da unidade nem demonstra um limite absoluto do hardware. [Antecipação existente e alternativas](../../t1_router_window/source.md)

**Reprodução.** Protocolo em `3f0e5948`, código em `4992d76d`. As duas execuções independentes (R01/R02) produziram recibos de SHA-256 `4a9f2f7c7985120323d5075521e7d89b67c9c08ec182baece3bcf499bd96340b`, iguais byte a byte. Custaram 0,60 s e 85 588 KiB RSS, e 0,59 s e 85 956 KiB RSS, respetivamente. O comando lê só journals, fontes e compactos. Os três testes sintéticos incluem uma claim e uma leitura em voo, poda, transição entre tiles, relógios invertidos e sensibilidade da banda.

```sh
python3 -IB test_screen.py
timeout 120 prlimit --as=805306368 python3 -IB screen.py \
  --archive-root "$PRIVATE_QUALIFICATION_ARCHIVE" \
  --cuts-receipt ../cuts-receipt.json \
  --backend "$C7/backends/c269-layer-last-use" \
  --new-output-dir "$NEW_RESULT"
```
