# A segunda camada de antecedência vale pouco tempo quando a largura permanece em quatro

**No P106, a 8 GB/s úteis, passar de uma para duas camadas de antecedência reduz o piso de serviço em apenas 2,076 ms quando se mantêm quatro identidades por destino.** O banco de frequência já cobre 150 das 567 primeiras procuras estritas. Se cada horizonte puder emitir quatro novas identidades para o mesmo destino, o piso desce mais 65,923 ms. A segunda previsão ganha sobretudo por alargar o conjunto que pode propor. Estes números comparam dois limites com previsão perfeita e janelas do mesmo pedido. O ganho de um preditor concreto depende também dos erros e do custo de o executar. [Protocolo](protocol.md) · [Recibo com ambos os relógios](receipt.json)

### O que o pedido admite

O alvo de prefill inclui apenas 375 primeiras procuras a buffers CPU e 192 a CUDA. Em cada uma, o próprio primeiro remap da camada pede uma geração ausente à entrada, o worker lê um registo do pack, faz três SET e publica-o antes do retorno. As 567 chaves correspondem a 7 495 286 400 B úteis. Os dois processos começaram com o mesmo estado dos 1 440 slots e produziram as mesmas 7 012 linhas de quatro ranks. As janelas e os relógios do cliente são os de cada processo. [População estrita](../README.md) · [Autoridade T1 e T2](../../prefill_retention/README.md)

O banco de frequência reduz o serviço de origem a 417 cargas, 5 512 406 400 B. Onze pertencem à camada zero e têm de esperar pela procura. O banco de recência reduz a 481 cargas. Em ambos os casos o banco continua a ser entregue ao primário, mas a simulação oferece esta entrega gratuitamente. A tabela dá o piso residual de serviço em **ms adicionais sobre o exterior das callbacks de prefill**, na hipótese mais favorável de disponibilidade do sinal. As colunas de P97/P106 usam preços em GB/s decimais e transporte fracionável partilhado entre CPU e CUDA.

| Banco e limite de identidades | Horizonte | P97 · 4,5 | P97 · 8 | P106 · 4,5 | P106 · 8 |
|---|---:|---:|---:|---:|---:|
| Sem banco, ilimitado | +1 | 287,327 | 83,765 | 280,620 | 82,755 |
| Sem banco, ilimitado | até +2 | 224,419 | 62,680 | 216,267 | 62,108 |
| Recência 353, ilimitado | +1 | 219,259 | 59,962 | 214,891 | 59,201 |
| Recência 353, ilimitado | até +2 | 168,629 | 46,442 | 165,221 | 45,912 |
| Frequência 353, ilimitado | +1 | 148,110 | 35,181 | 141,851 | 35,058 |
| Frequência 353, ilimitado | até +2 | 99,117 | 22,844 | 96,005 | 22,807 |
| Frequência 353, quatro por destino | +1 | 245,051 | 94,675 | 238,792 | 94,611 |
| Frequência 353, quatro por destino | até +2 | 201,933 | 92,534 | 198,821 | 92,534 |
| Frequência 353, quatro por horizonte e destino | até +2 | 110,868 | 26,915 | 107,755 | 26,611 |

No P106, com frequência e largura ilimitada, o horizonte +1 pode adiantar 4,874/5,232 GB dos 5,512 GB a 4,5/8 GB/s. Com duas camadas passa a 5,080/5,330 GB. Ainda ficam fora do prazo **432,021/182,459 MB**. No limite de quatro por alvo, 361 das 417 chaves têm uma licença de previsão em ambas as profundidades. Admitir quatro por horizonte aumenta para 404. A camada 1 só recebe +1 de L0, sem herdar tempo da tile anterior. As contagens de quatro por alvo ou horizonte pressupõem um limite agregado de emissão. Um top-4 por posição pode envolver mais de quatro experts distintos numa tile.

### O sinal existe antes do prazo?

No C291, `src/models/openai-moe.cpp` constrói o operando pós-atenção pela atenção, soma residual e RMS. A saída das waves e o residual alimentam a camada seguinte. `src/llama-graph.cpp` constrói o router a partir desse operando e faz depender a wave seguinte da anterior. O journal regista o primeiro REMAP_BEGIN e todas as linhas RANKS da camada fonte. No último desses RANKS já se conhece toda a seleção original. O PFJ não regista o timestamp de produção do post_norm, a permanência desse tensor até ao remap ou o seu custo de acesso no backend do preditor. O começo da tile para uma fonte L0, ou o último REMAP_END da camada que precede a fonte, fornece a fronteira anterior otimista. A tabela acima quantifica essa concessão. [SHA dos dois construtores](receipt.json) · [Marcadores PFJ](../../../observer.patch) · [Sonda CPU no GET_ROWS](../../../../../../../router_ready_probe/README.md)

Se a previsão só puder começar no último RANKS efetivamente observado, P106 com frequência/ilimitado e +2 deixa 102,227/24,559 ms, em vez de 96,005/22,807 ms. Assim, adiantar o próprio marcador até à fronteira favorável muda o piso em **6,223/1,752 ms** a 4,5/8 GB/s. Esta diferença não localiza o verdadeiro post_norm. A primeira remap do destino é o prazo deste crivo. Uma leitura que se conclua posteriormente pode ainda reduzir uma espera de serviço, mas já não antecipou integralmente essa parte ao primeiro remap.

As janelas de camadas vizinhas sobrepõem-se. EDF concede o recurso disponível ao pedido libertado com o prazo mais próximo, interrompe-o sem custo e descarta o saldo expirado. A troca de um byte de prazo posterior por um já libertado de prazo anterior permite atingir o máximo fracionável sem criar largura adicional. No relógio original P106, frequência/+2/ilimitado, 5,367 GB podem chegar antes do prazo a ambas as taxas. Este resultado usa inclusive as esperas que a intervenção pretende eliminar. Eliminando todas as callbacks da linha temporal, o teto cai para os 5,080/5,330 GB acima. O volume que excede a capacidade desse exterior impõe tempo adicional num caminho com essa taxa. Esta inferência preserva dependências, tempos exteriores e a sequência de releases. Um novo produtor que altere o grafo ou o ritmo do exterior precisa de nova medida.

### Consequência para a conversa e custo da previsão

Mesmo concedendo todo o ganho de decode antes da primeira peça, frequência/+2/ilimitado a 8 GB/s exige **7,234 tok/s no P97 e 8,487 tok/s no P106** para cumprir os dois alvos. A 4,5 GB/s os mínimos são 7,320/8,600 tok/s. A 8 tok/s no P106 ainda faltam **336,965 ms** a 8 GB/s e **410,162 ms** a 4,5 GB/s. A 6 tok/s faltam 2,295/2,368 s no mesmo processo. A 10 tok/s sobrariam 838,035/764,838 ms, respetivamente, para todo o trabalho extra exposto. A selagem pré-stream continua incluída no relógio do cliente P106. O orçamento supõe que se cumpra aquela velocidade sem perder paridade, e continua a oferecer os restantes misses, filas, cópias e SET. [Separação dos relógios nas duas conversas](../../prefill_retention/repeat/README.md)

| Avaliação densa do router de destino | Linhas/destino | MAC (2 880 × 128 por linha) | Matrizes F32 distintas | Linhas entre tiers | Operando F32, se copiado |
|---|---:|---:|---:|---:|---:|
| Próxima camada | 5 203 | 1 918 033 920 | 35 · 51 609 600 B | 153 | 1 762 560 B |
| Segunda camada | 5 050 | 1 861 632 000 | 34 · 50 135 040 B | 306 | 3 525 120 B |

As duas profundidades juntas dariam 3 779 665 920 MAC antes de norma, bias, top-k, sincronização e confirmação. As 34 matrizes da segunda profundidade estão entre as 35 da primeira e podem ser reutilizadas. Na chamada 5 e nas cinco tiles da 148, as linhas/destino são 170, 1 088, 1 088, 1 088, 1 088, 681 para +1 e 165, 1 056, 1 056, 1 056, 1 056, 661 para +2. A camada 35 só calcula uma posição. Calcular no dispositivo da fonte, reter o operando ou partilhar a cópia entre dois destinos altera o transporte. Os MAC e bytes não têm preço em segundos nesta análise. [Contrato da contagem](projection.md)

O banco de frequência implicaria 1 126/423 cópias CPU/CUDA no T1, 14,885/5,592 GB. Na agenda completa do prefill teria 171/126 reposições, e no decode 41/35. Para a recência são 3 238/1 268 cópias de T1 e 143/29 reposições de decode. Qualquer produtor de previsão ainda deve proteger os slots em uso, as gerações, a memória temporária e o decode. Em particular, é necessário medir se uma segunda projeção, staging e leituras desperdiçadas custam menos do que o ganho marginal na política de largura escolhida. Em C309, as oito execuções pagaram o staging só no decode em CPU2–24, a partir de um sinal pré-atenção; os 377–479 READs inúteis por braço acompanharam regressões. Esse resultado permanece aplicável àquela arquitetura. No C270 o controlo do projetor pós-atenção original falhou uma linha de prefill CUDA entre 3 400 linhas totais. A calibração posterior desse sítio e a velocidade nesta conversa são perguntas distintas. [C309](../../../../../../../../C309-UNTRAINED-STAGING-COST-NO-GO-20261007.md) · [Controlo do projetor](../../../../../../../router_lookahead/README.md)

**Decisão.** Com estes exteriores e um decode de 6 ou mesmo 8 tok/s no P106, um preditor de prefill até duas camadas não basta. Para isolar o mérito arquitetural de +2, manter a largura total sob controlo e observar a hora de produção do post_norm, a chegada do peso no destino correto, o custo de gerar a previsão e o trabalho deslocado antes do primeiro final. A confirmação dos ranks e a duração do decode têm de ser verificadas no mesmo alvo. A estimativa fracionável permite decidir essa fronteira sem atribuir desempenho natural ao ensaio C270.

### Reprodução

Pré-registo `ecf931d6`, contagem aritmética `bcecaca3`, código `6c2664fc`. Os dois processos leram apenas journals, fontes do grafo e recibos, em 1,30/1,31 s com RSS 52 840/53 036 KiB. Os recibos de 134 042 B foram idênticos, SHA-256 `cb100940b5b5eeae519b534b54667ce4f5147cf8f006d86e2ab8ed26fdfa624a`. Quatro testes incluem enumeração exata em 216 populações sintéticas, concorrência entre prazos, fronteiras L0/L1, carga que desaparece com a contração da espera e ausência do marcador. [Código](screen.py) · [Testes](test_screen.py)

```sh
timeout 90 prlimit --as=536870912 --cpu=90 -- python3 -IB screen.py \
  --archive "$PARTS" --backend "$C291" --new-output-dir "$FRESH/run01"
timeout 90 prlimit --as=536870912 --cpu=90 -- python3 -IB screen.py \
  --archive "$PARTS" --backend "$C291" --new-output-dir "$FRESH/run02"
python3 -IB compact.py --first "$FRESH/run01/receipt.json" \
  --second "$FRESH/run02/receipt.json" --new-output "$FRESH/compact.json"
cmp "$FRESH/compact.json" receipt.json
```
