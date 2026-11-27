# Um executor novo para começar pelos experts disponíveis?

**NO_GO para investir num backend dedicado com quatro workers e um banco fixo adicional de 353 experts, mantendo as dependências e os custos observados. GO local para o operador experimental.** Na CPU do portátil, iniciar os três ranks já residentes durante a leitura do quarto poupou 0,328 e 0,513 ms face ao operador de quatro ranks, nas medianas de dois blocos. No pedido nominal, mesmo com as melhores chaves retrospetivas e acesso gratuito ao banco nos hits, o certificado de P106 dá pelo menos **10,104750168 s** até ao primeiro conteúdo final. O objetivo é 10 s. R0 `slots40-persistent` continua a ser o controlo. M3 PARTIAL e M4 NOT_MET. [Recibo compacto com todos os braços](evidence/decision.json)

## Cálculo e leitura no portátil

A [unidade seguinte](../renewal/README.md) executou o teste de renovação aqui proposto. Identificou os consumidores posteriores de todas as 436 leituras antecipadas, verificou a capacidade de 353 lugares, cruzou o desconto das waves vazias com o mesmo caminho crítico e mediu o leitor alternativo no NVMe do portátil.

**MEDIDO** em CPU0, no primeiro decode de C270, posição 189. O router do target reproduziu os 128 logits, o vetor após bias, os IDs [28,24,8,16] e os pesos dos quatro ranks. No instante capturado, e28, e8 e e16 estavam residentes e faltava e24. O protótipo mantém os slots físicos [3,14,6,35], lê a janela de e24 com um único `pread` O_DIRECT de 13 221 888 B e faz três SET, somando 13 219 200 B. Os três modos usam os mesmos bytes MXFP4, oito threads GGML e quatro workers de serviço persistentes. A variante READY usa um serviço especializado nesta única falta, com publicação por geração. O ensaio cobre a fronteira desde a emissão da procura já encaminhada até à soma na ordem lógica e ao drain dessa procura. As equipas e os grafos já existem no início de cada intervalo. [Referência independente das contribuições](../../qualification-retake/igpu_resident_rank/projection/rank_cpu/README.md) · [Código nativo](native.cpp)

| 7 triplos por bloco, mediana em ms | FULL espera e calcula 4 | WAIT espera e calcula 3+1 | READY começa pelos 3 | FULL − READY emparelhado | WAIT − READY emparelhado | Interseção entre o grafo dos 3 e o READ |
|---|---:|---:|---:|---:|---:|---:|
| FULL, WAIT, READY | 6,006 | 6,024 | 5,626 | +0,328 | +0,461 | 0,621 |
| READY, WAIT, FULL | 6,157 | 6,219 | 5,730 | +0,513 | +0,598 | 0,663 |

Os dois contrastes favoreceram READY em 13 dos 14 triplos. Ambos inverteram o sinal no mesmo triplo do primeiro bloco. A interseção usa os relógios do host que envolvem o grafo sincronizado e a materialização das três contribuições, e a entrada/saída do `pread`. O tempo ocupado do controlador NVMe permanece desconhecido. As duas colunas de ganho mostram a mediana da diferença dentro de cada triplo. Cada uma das 3 execuções prévias e 42 cronometradas reproduziu bit a bit as 11 520 palavras F32 das contribuições e as 2 880 do FFN. Trocar as contribuições 0 e 2 alterou 720 palavras do FFN. A colocação dos outros experts, o custo do router e o serviço completo do primeiro turno ficam fora deste relógio de operador. [Protocolo congelado](protocol.md) · [Supervisor e verificador](physical.py)

## O relógio da conversa

**TRACE_DERIVED** para dois processos com a mesma conversa, 2 044 tokens de histórico reutilizados, 153 novos e 47 IDs no decode. A captura de CPU0 acima pertence a uma trajetória independente. Os PFJ autenticados de P97 e P106 mantêm 48 chamadas, 2 987 callbacks e 2 354 gerações. O limite cobra 1 918 gerações, todos os SET salvo na concessão explícita de acesso direto, e oferece gratuitamente 436 cargas. Cada chamada conserva o trabalho exterior e o cleanup do protocolo original. As 44 avaliações de decode anteriores ao primeiro final entram em ambos os relógios. [Fronteira do cliente e custos por fase](../protocol.md)

| Primeiro conteúdo final em s | P97 | P106 | Decode P97 / P106, s por 47 IDs |
|---|---:|---:|---:|
| Observado, trace-ON | 18,326 | 19,529 | 8,947 / 9,214 |
| Mesmas 353 chaves do #51, exterior móvel em toda a chamada | 9,118 | 9,864 | 5,447 / 5,249 |
| Mesmas chaves, exterior móvel até à camada vizinha | **11,030** | **11,803** | 6,191 / 6,121 |
| Limite certificado para qualquer banco de 353, com SET nos hits | 9,345 | **10,367** | 4,774 / 4,933 |
| Limite certificado para qualquer banco de 353, SET gratuito nos hits | 9,099 | **10,105** | 4,571 / 4,708 |

Os valores da tabela estão arredondados ao ms. Cada grupo é uma camada de um tile. O router seguinte precisa da redução anterior. O modelo deixa o trabalho entre callbacks vizinhos repartir-se entre os dois lados de cada fronteira. Assume que esse trabalho de grafo e os preços de serviço permanecem como no trace. Um novo kernel, acesso antecipado entre camadas, outra divisão por dispositivo ou uma mudança no custo do cliente altera as premissas. O teste em que todo o exterior da chamada pode mover-se reproduziu exatamente os dois relógios do #51. Abaixo do limite de um relógio pode ainda faltar desempenho real para passar. O braço código, a sessão sustentada e a neutralidade de instrumentação da arquitetura candidata ficam por qualificar. [Cálculo e conservação](causality.py) · [Controlo de custo trace-OFF](../../qualification-retake/packed_nvme_manifest/server_profile/conversation/ordens.md)

O maior serviço obrigatório antes do primeiro final com as chaves do #51 ocorre no prefill da chamada 2, tile 1. P106 aponta para a camada CPU 15, com 11 jobs e piso de 53,193 ms. P97 aponta para a camada CUDA 32, com 11 jobs e 57,708 ms. Estes máximos são de serviço no modelo. A influência individual destas camadas na latência física requer uma captura com ativações e eventos de execução no mesmo local. Nenhum ganho de CPU0 foi multiplicado por camadas ou tokens.

**FORMAL, condicional aos preços e à localidade.** Os certificados permitem escolher o banco mais favorável para cada processo e cada relógio separadamente, até com frações de experts. O verificador usa inteiros e confere os pesos de cada desigualdade. Em P106 o certificado com SET continua a excluir o alvo até 413 entradas e o direto até 369. Para vencer esta prova alterando apenas a capacidade seriam necessárias pelo menos 414 ou 370 entradas, respetivamente. São mais 806 371 200 ou 224 726 400 B de payload. A reserva dessa memória e a existência de uma política que a aproveite continuam por provar. [Método](certificate.md) · [Certificados inteiros](evidence/certificate.json.gz)

## Dois ganhos podem combinar-se

O cliente de P106 gastou 645,215 ms a selar o estado de T1 e 646,428 ms entre o início do relógio e a entrada no stream. A localização desse trabalho já estava medida. Falta determinar quanto uma política causal consegue eliminar e que custo passa para o primeiro turno. O intervalo completo continua pago no veredito principal. A experiência seguinte dá a P106 até 646,428 ms de crédito e mantém os outros três relógios. [Medição da selagem](../../qualification-retake/igpu_resident_rank/request_budget/device/pack_native/natural_trace/prefill_retention/repeat/README.md) · [Protocolo da combinação](client-cost.md)

| Banco e concessão | P97 primeiro final, s | P106 primeiro final com todo o crédito, s | Decode P97 / P106, s |
|---|---:|---:|---:|
| Melhor testemunha inteira encontrada com SET | 9,784 | 10,003632 | 5,388 / 5,431 |
| Testemunha inteira com acesso direto e seleção retrospetiva | **9,645** | **9,870** | 5,253 / 5,298 |
| Recência em T1, direto | 11,710 | **12,041** | 6,892 / 7,019 |
| Frequência no prefill de T1, direto | 11,857 | 12,185 | 7,146 / 7,259 |
| Tempo da reserva à publicação em T1, direto | 11,871 | 12,177 | 6,983 / 7,100 |

A testemunha direta exige recuperar **516,436 ms** dos 646,428 ms para caber nos quatro prazos do simulador. Sobram no máximo 129,992 ms em P106 para todos os custos omitidos. Com SET a melhor testemunha encontrada ainda falha por 3,632 ms com o crédito completo. A existência de outro banco com SET que passe essa sensibilidade ficou INCONCLUSIVE. Nas três políticas causais concedemos também custo zero de aquisição do banco. A melhor ainda precisa de ganhar **2,041 s em P106 e 1,710 s em P97**, mesmo após todas as concessões. Os dois ganhos isolados só podem ser somados se incidirem em trabalho distinto do caminho crítico. [Chaves agregadas das testemunhas, sem sequência de tokens](evidence/oracle-banks.json) · [Controlo T1 e avaliação T2](causal_controls.py)

**Condição de reabertura.** Uma política que conheça apenas o passado tem de demonstrar no pedido esse ganho adicional, com cópias, contenção e selagem pagos. O próximo discriminante barato é medir num replay causal se renovar o banco dentro de T2, usando apenas bytes já entregues pelo target, consegue cobrir a diferença com os mesmos 353 lugares. Esta experiência permite decidir se vale a pena integrar o operador de sobreposição no backend existente. Um novo backend completo exigiria identificar uma fronteira do backend atual que impeça essa integração ou outro ganho demonstrável. Nesta unidade, o próprio GGML executou o operador exato.

**Antecedente consultado em 27 de novembro.** O PagedMoE já inicia experts prontos na CPU enquanto o SSD fornece os restantes. A sua implementação usa SGLang com batch 1 e quantização por planos de bits. No controlo Fixed4 com cache de 24 GiB, os autores ainda medem 87,16 ms/token de I/O exposto depois da sobreposição. A contribuição aqui é o contraste com a mesma partição do grafo, o contrato MXFP4 original e um limite verificável na conversa do portátil. O Bevy também sobrepõe trabalho útil, com vários pedidos concorrentes. [PagedMoE, §§3 e 7–8](https://arxiv.org/html/2611.03173v1) · [Bevy, §§4–5](https://arxiv.org/html/2611.04794v1)

## Proveniência e reprodução

O Git fixou o protocolo em `8bdb6288` antes de avaliar o candidato. O código físico correu no commit limpo `adcbbd49bab352499527f129a1b9adbed652b44a`, árvore `1eccfd8f6fe1a64a14c09db84f335921219d2599`. O ELF tem SHA-256 `dc1298ec0fc8fbfba6b18d2039b835241d25607dd5bb315412d0ca4e0743915b`. O invólucro usa a compilação C291 e as bibliotecas CPU/base C269 autenticadas pela receita da referência. O build regista as identidades do compilador, das bibliotecas e dos fontes. O portátil tinha Ryzen AI 9 HX 370, RTX 4060 Laptop com 8 188 MiB, driver 620.73.04 e pack no NVMe interno. A C55 passou em AC/performance. A C118 mediu 60,176 s antes do arranque. O filho físico levou 0,403 s. O pico do cgroup foi 132 476 928 B sob cap de 4 GiB e swap zero. Os sensores registaram na C55 até 61,25 °C na CPU, 45,64 °C na GPU e 37,85 °C no NVMe. O ensaio leu 648 019 968 B lógicos do pack incluindo preparação. A energia por triplo e os bytes físicos por expert não foram instrumentados. Zero arranques do servidor 120B e zero cálculo GPU nesta unidade.

O arquivo privado exclusivo `outputs/ready-layer-20261127-01` tem 27 ficheiros e 501 460 B antes do manifesto. O manifesto tem SHA-256 `36257ad557533044a2dd29fab83fe759ac9d8cfe4d26f995c9d76d4087359c07`. A primeira execução física parou antes do cálculo porque a cópia arquivada da preparação só tinha o recibo. O segundo scope usou os ficheiros originais do portátil após conferir os três hashes. A primeira proposta de certificado também parou antes da otimização porque NumPy não estava visível no Python isolado. A repetição usou Python 3.14.10, NumPy 2.4.6 e SciPy 1.17.1 já instalados. O verificador standard reproduziu os certificados e as testemunhas sem o solver. As duas falhas estão no arquivo. [Recibo, hashes e tempos individuais](evidence/decision.json)

No clone completo, `TESY_ARCHIVE` designa o arquivo privado dos PFJ P97/P106 e `TESY_LAYER_ARCHIVE` o desta unidade. Cada execução cria uma subpasta nova.

```sh
study=research/ready-experts/layer
out=$(mktemp -d)
python3 -IB "$study/causality.py" --archive "$TESY_ARCHIVE" --new-output-dir "$out/causality"
python3 -IB "$study/all_banks.py" --archive "$TESY_ARCHIVE" --verify "$study/evidence/certificate.json.gz" --new-output-dir "$out/proof"
python3 -IB "$study/client_cost.py" --archive "$TESY_ARCHIVE" --verify "$study/evidence/oracle-banks.json" --new-output-dir "$out/combined"
python3 -IB "$study/causal_controls.py" --archive "$TESY_ARCHIVE" --new-output-dir "$out/controls"
python3 -IB "$study/compact.py" --archive "$TESY_LAYER_ARCHIVE" --new-output-dir "$out/public"
cmp "$out/public/decision.json" "$study/evidence/decision.json"
python3 -m pytest -q tests/test_ready_expert_layers.py
```

Para gerar novas propostas com SciPy, omitir `--verify` e usar outro destino. A otimização conjunta consumiu 18,76 s de parede e 149 992 KiB de RSS. O recibo dos três controlos foi obtido em `7322b5d8`. A repetição depois de abreviar a docstring para a lint reproduziu todos os campos exceto o hash do próprio fonte.

Para a medição física, partir do commit físico indicado acima e dos inputs de [rank_cpu](../../qualification-retake/igpu_resident_rank/projection/rank_cpu/README.md). Usar `layer/build.py` com os mesmos `--old-build` e `--libs`. Correr `nvme_admission/window.py` com o GGUF no NVMe e exigir PASS. Em scope dedicado com MemoryMax/MemoryHigh=4G, MemorySwapMax=0 e RuntimeMaxSec=370, executar `layer/physical.py` com os argumentos de [rank_split](../../qualification-retake/igpu_resident_rank/projection/rank_split/README.md), novos identificadores e hashes de build e C55. O diretório `--input-dir` tem de conter os dois ficheiros do router além de `prepare.json`. A CI só precisa das fixtures matemáticas sem modelo.
