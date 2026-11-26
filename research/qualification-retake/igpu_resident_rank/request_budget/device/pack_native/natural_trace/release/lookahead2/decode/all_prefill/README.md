# Cobrar todos os pesos de prefill muda a decisão no P106

**Com as 1 263 reservas de prefill, previsão perfeita de quatro identidades a uma camada, FREQ353 e 4,5 GB/s, o primeiro final do P106 ultrapassa 10 s em pelo menos 325,789 ms se a emissão começa nos RANKS observados.** A margem anterior de 684,248 ms cai 1 010,037 ms. O decode ainda admite 3 345,304 ms de custo novo antes de cair abaixo de 6 tok/s. A libertação mais favorável ao predictor e ao router do próprio alvo, ambos tão cedo quanto o grafo permite, deixa **262,365 ms** até ao primeiro final. A localização real do sinal e o preço da implementação decidem entre estes dois cenários. [Recibo dos dois pedidos](receipt.json) · [Orçamento anterior](../README.md)

### O que faltava cobrar

P97 e P106 têm as mesmas 1 263 gerações de prefill e 1 091 de decode, com as mesmas chaves, reservas e primeiras waves consumidoras. Há **827 demandas diretas e 436 preloads** em prefill. Cada preload observado pertence à wave imediatamente seguinte da mesma camada e tile; os seus bytes podem chegar até ao fim do remap que aí os exige. Encurtar o prazo para a wave que o reserva cobraria transporte que pode decorrer em paralelo. A primeira reserva de 852 chaves encontra-as ausentes à entrada, 199 recebem uma nova reserva apesar de terem entrado residentes, e 212 são reservas repetidas de uma chave já carregada. Cada geração tem um READ e três SET com a publicação comprovada antes do uso. [Atribuição e revisões de fonte](screen.py) · [Protocolo](protocol.md)

| População de prefill | Pack CPU | Pack CUDA | Banco CPU | Banco CUDA |
|---|---:|---:|---:|---:|
| 567 primeiras procuras estritas anteriormente cobradas | 274 | 143 | 101 | 49 |
| 696 reservas adicionais | 363 | 186 | 70 | 77 |
| Todas, staging transitório | 637 | 329 | 171 | 126 |

Com staging transitório, o prefill precisa de 966 payloads do pack, **12 769 747 200 B**. No P106 com libertação observada a 4,5 GB/s, a ligação comum aos dois dispositivos pode entregar antecipadamente até 7 044 742 512 B. Os prazos e a largura dão um piso de **1 272,223 ms expostos de transporte**. A sensibilidade aos SET eleva o piso conjunto para 1 274,321 ms, tomando por avaliação o maior de dois pisos de recursos concorrentes. A sensibilidade permite SET de preload durante o exterior da callback; o piso exclusivo dos SET é 314,282 ms. No decode contam-se as mesmas 1 015 chegadas do pack e 76 do banco enquanto o staging for transitório.

### Margem para todo o custo exposto que ainda falta

Cada par é **primeiro final / decode**, em ms, com SET ao preço observado e staging transitório. As duas colunas de 4,5 e 8 GB/s são hipóteses de taxa útil do mesmo link. A largura quatro aplica-se ao conjunto antecipado de cada tile/destino; após obter a rota verdadeira, todas as chaves do próprio destino podem avançar. A fronteira anterior concede esse acesso local mais cedo, além de adiantar a previsão. L0 recebe exclusivamente o sinal local.

| Sinal, largura | P97 · 4,5 | P106 · 4,5 | P97 · 8 | P106 · 8 |
|---|---:|---:|---:|---:|
| RANKS local, sem previsão | −1 256,22 / +2 573,50 | −2 475,47 / +2 275,80 | +1 197,50 / +3 877,97 | −31,03 / +3 580,28 |
| RANKS observado, +1/4 | +759,62 / +3 523,16 | **−325,79 / +3 345,30** | +2 754,65 / +4 739,43 | +1 548,45 / +4 459,32 |
| Fronteira anterior, +1/4 | +1 315,10 / +3 954,33 | **+262,36 / +3 786,65** | +3 033,54 / +4 859,95 | +1 779,72 / +4 516,89 |
| Fronteira anterior, +1 ilimitado | +1 373,78 / +3 954,33 | +324,58 / +3 786,65 | +3 070,86 / +4 859,95 | +1 795,04 / +4 516,89 |

A ausência de preço de SET melhora o primeiro final P106 a 4,5 GB/s, +1/4 na rota observada, apenas de −325,789 para −323,691 ms. Para reabrir esse regime pela chegada mais cedo dos pesos, é necessário recuperar pelo menos o défice **antes da primeira peça**, além de pagar a execução do predictor, transferências e sincronização expostas. No extremo de libertação anterior, p+x pode somar no máximo 262,365 ms, e x+y no máximo 3 786,647 ms; p é prefill, x são as 44 avaliações até à primeira peça e y as duas últimas. A margem de P97 usa o FREQ obtido no T1 de P106, transportado após verificar a igualdade dos sítios e do estado. Nenhuma comparação transfere tempos entre P. [Relógios e denominações](../protocol.md)

### Quando uma recarga pode sair de RAM

O C291 reserva um staging alinhado por worker, reutilizado a cada leitura. Conservar a última chave no próprio buffer e invalidá-la quando se usa o banco **dá zero hits nas quatro threads** dos dois pedidos, incluindo o decode. A conclusão é específica dessa atribuição a workers. Um cache associativo partilhado ou outra distribuição chama outra política de pin e sincronização. As duas linhas seguintes distinguem políticas que conservam todos os bytes e compram armazenamento adicional além do banco. A seleção de cada página usa apenas o READ observado ou a vítima READY antes da substituição. O valor de memória é payload lógico; alinhamento de I/O direto, metadados e leases somam-se.

| Staging no P106, +1/4, RANKS, 4,5 GB/s | Prefill pack / staging / banco | Páginas extra no carry / fim | Pico extra de payload | Margens primeiro final / decode | Margem do primeiro final com decode anterior fixo |
|---|---:|---:|---:|---:|---:|
| Transitório ou quatro tags privadas | 966 / 0 / 297 | 0 / 0 | 0 B | −325,789 / +3 345,304 ms | −325,789 ms |
| Reter todos os READ não bancários | 824 / 142 / 297 | 824 / 1 477 | 19 524 758 400 B | +697,210 / +4 037,360 ms | **+10,651 ms** |
| Reter READs e vítimas READY | 642 / 324 / 297 | 1 270 / 1 613 | 21 322 569 600 B | +1 529,760 / +4 490,641 ms | +395,225 ms |

No primeiro destes modos que retêm tudo, já há **10 892 620 800 B adicionais** ao terminar o prefill; no segundo há **16 788 384 000 B**, incluindo 432 vítimas CPU e 196 CUDA capturadas. Estas 196 capturas requerem acesso aos bytes residentes na GPU e exportação para o host se o backing estiver em RAM. As estimativas concedem tempo zero à conservação e ao custo de memória; ambas as políticas compram novo espaço físico. O ganho de 697,210 ms é principalmente de reaproveitar os bytes no decode. Na ablação que paga apenas as leituras conservadas em prefill, com o preço anterior de decode, a folga de 10,651 ms é para todo o resto. O banco inicial de 353 chaves mantém as suas aquisições de T1 em todos os modos.

**Decisão.** Com a agenda e a memória transitórias correntes, o prazo dos RANKS observados refuta as duas metas em conjunto no P106 a 4,5 GB/s. A fronteira temporal mais cedo ou um backing que preserve chaves entre gerações podem mudar o veredito. O dado discriminante é o tempo de chegada do peso à camada consumidora, incluindo o custo de produzir a previsão, ou a cobertura sob um limite explícito de páginas extra fisicamente disponíveis. A previsão perfeita, o EDF fracionável, o porte fixo do exterior e os 4,5/8 GB/s são condições deste limite.

### Auditoria e reprodução

Pré-registo `c605c79e`. R01 com fonte `9df223e8` recusou o primeiro preload antes de produzir preços. O revisor confundia o reason 1 de promoção com o reason 2 do primeiro enqueue de preload. O recibo negativo tem SHA `e1e901b865297a96eb97952d2ee68827dea9827fe33842a77b0f6aeed2ba7891` (3,51 s, 58 800 KiB). A fonte `05e7c154` confere o reason original, a identidade e a distância de uma wave. R02/R03 produziram 79 786 B idênticos, SHA `ed035fcfa6a98e12ec7bbef29343256caa7c857f942d3ffa689e4bb562974147`, em 3,98/4,01 s com RSS 64 576/64 828 KiB. Os cinco testes incluem preload com SET oculto, contraprova de reason, controlo de memória por worker, retenção através do carry e comparação enumerativa das licenças. A revisão lê as partes 97/106 e a fonte C291. [Testes](test_screen.py) · [Compactação](compact.py)

```sh
python3 -IB test_screen.py
timeout 90 prlimit --as=536870912 --cpu=90 -- python3 -IB screen.py \
  --archive "$PARTS" --backend "$C291" --new-output-dir "$FRESH/r02"
timeout 90 prlimit --as=536870912 --cpu=90 -- python3 -IB screen.py \
  --archive "$PARTS" --backend "$C291" --new-output-dir "$FRESH/r03"
python3 -IB compact.py --first "$FRESH/r02/receipt.json" --second "$FRESH/r03/receipt.json" \
  --new-output "$FRESH/compact.json"
cmp "$FRESH/compact.json" receipt.json
```
