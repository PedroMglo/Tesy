# A fila do C292 distingue o prefill CPU do decode

**No prefill CPU, 421 das 562 ofertas identificam a geração que acaba por ser pedida. Todas as 421 janelas de 13 221 888 B caberiam antes do prazo, mesmo pausando a FIFO durante cada READ original do pack.** No decode, a mesma FIFO global só termina **3 das 815 ofertas corretas** nessa sensibilidade. O sinal admite testar o produtor e a entrega nativa no prefill CPU. O C292 mediu a hora da previsão e da procura real, efetuou **zero leituras especulativas** e confirmou os bits dos dois braços. [Recebimento observado e comparação numérica](../README.md) · [Recibo do crivo](receipt.json)

| Destino na captura de 189+32 | Sítios | Ofertas após corte de quatro | Gerações correspondentes | FIFO com link livre | FIFO fora de READ nativo | Teto local fora de READ |
|---|---:|---:|---:|---:|---:|---:|
| Prefill CPU | 144 | 562 | 421 | 421 | **421** | 421 |
| Prefill CUDA | 61 | 232 | 185 | 185 | **180** | 182 |
| Decode CPU | 768 | 836 | 588 | 428 | **2** | 130 |
| Decode CUDA | 352 | 280 | 227 | 162 | **1** | 46 |
| Total | 1 325 | 1 910 | 1 421 | 1 196 | **604** | ≤779 |

O prazo principal é o primeiro entre a aceitação do job pelo worker (E13) e o início da barreira da primeira wave consumidora (E19). A fila usa o último E33 real de cada sítio, filtra slots READY e LOADING no destino, ordena pelo número de votos com desempate pelo ID e envia até quatro ofertas. Só se credita a primeira geração reservada posteriormente e realmente consumida nessa tile. Há 511 sítios com janela válida que se sobrepõe a pelo menos uma janela anterior para o prazo principal, em ambos os relógios. Somar os ótimos locais concede largura repetida; a coluna FIFO partilha um só cursor por todos os sítios, incluindo os falsos. [Protocolo](protocol.md) · [Política e prazos](../../../../demand/deadlines/score.py)

Em todas as fases, 489 ofertas da fila não encontram uso, **6 465 503 232 B**. Restringir a emissão exclusivamente aos 144 sítios de prefill CPU mantém as 421 chegadas em ambos os cenários. Esse filtro compra **7 430 701 056 B** em 562 leituras, incluindo 1 864 286 208 B nas 141 ofertas falsas. As 421 entregas úteis valem 5 566 414 848 B de janela; o limite refere-se à conclusão da leitura no staging. Para substituir o READ original é ainda preciso integrar a chegada, os três SET e o PUBLISH no slot/geração corretos e provar que nenhum leitor antigo perdeu os seus bytes. No prefill, 233 das 421 gerações de CPU e 106 das 185 de CUDA foram reservadas para uma wave posterior. No pedido real, as 4 501 leituras foram todas emitidas pelo manager original, incluindo os seus próprios preloads.

### O que significam os 1 803 acertos anteriores

A auditoria anterior encontrou 1 803 gerações ausentes cujo expert aparecia entre todas as previsões individuais antes do lookup E34. Nesta pergunta, uma oferta parte só após dispor da votação da tile e verifica o estado que existe **nesse** instante. Mesmo antes do corte de quatro, há 4 494 chaves candidatas depois do filtro e 3 262 ocorrências encontram uma nova geração no seu destino, incluindo 1 728 ainda ausentes no primeiro lookup e 1 534 que já estavam LOADING ou READY nesse lookup. A reserva nativa que as pôs nesse estado ocorreu depois da emissão, o que permite confrontar ambos os produtores com o mesmo prazo. Após o corte são 1 082 acertos ausentes no lookup e 339 já em carga ou prontas. Nem os 1 803 nem os 1 421 demonstram que a leitura terminou a tempo. [Auditoria E33/E34](../join.py)

A 4,5 GB/s, uma janela inteira exige pelo menos **2,9382 ms** no link disponível. O cenário livre concede o recurso completo à fila auxiliar. O cenário residual mantém as 4 501 leituras da agenda original: a união E30 ocupa 22,923 s e os quatro workers somam 69,841 worker-s. A mesma transformação de tempo subtrai a união tanto à emissão como aos três prazos, com pausa e retoma gratuitas. No segundo cenário, apertar o prazo até à **reserva** (E11) ainda dá 421/180/2/1 chegadas FIFO, por ordem da tabela; no cenário livre o decode CPU baixa de 428 para 427. Os números do teto local e a contagem de janelas sobrepostas para todos os prazos constam do recibo.

No ON, E32→último E33 somou **1,783 s no prefill e 0,605 s no decode**. Estes intervalos do host já incluem as GET, preparação e projeção. Os intervalos nativos de entrada a retorno somaram 22,814 s e 8,455 s, respetivamente. O tempo de processo reportado foi 33,092 s OFF e 34,285 s ON em dois lançamentos de ordem fixa; inclui também trabalho do cliente de captura. As janelas desta sonda síncrona não demonstram o tempo disponível num servidor de callback nulo. O próximo teste discriminante de prefill CPU precisa observar a conclusão real do READ, reuso dessa geração pelo consumidor e bytes falsos num orçamento de staging limitado.

### Reprodução

Protocolo `d3e41afc`; fonte e testes `8a5e674d`. O revisor autentica família `e762554f…`, braço ON, revisor independente `fa9490ac…` e os 102 678 registos do journal `cc2b79a1…`. Reabre o join completo, as 4 501 gerações e as 38 tiles com os limites das waves e a colocação. Usa a função de seleção do estudo de procura e o escalonador de prazos já verificado. R01/R02 produziram os mesmos 16 168 B, SHA-256 `99ae0a8f90275caf122117cbc1acb466e84ffaa5426370380bbc9c05fc092701`, em 0,57 s cada e 85 744/85 620 KiB de RSS. Três testes incluem sobreposição de janelas e READs, transformação dos dois extremos, empate de votação e backlog de palpites falsos. [Código](screen.py) · [Testes](test_screen.py)

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
"$TESY_REPO/.venv/bin/python" -IB test_screen.py
nice -n 10 taskset -c 4 timeout 90 prlimit --as=536870912 --cpu=90 -- \
  "$TESY_REPO/.venv/bin/python" -IB screen.py --family "$C292" \
  --review-receipt "$REVIEW/receipt.json" --new-output-dir "$FRESH/r01"
nice -n 10 taskset -c 4 timeout 90 prlimit --as=536870912 --cpu=90 -- \
  "$TESY_REPO/.venv/bin/python" -IB screen.py --family "$C292" \
  --review-receipt "$REVIEW/receipt.json" --new-output-dir "$FRESH/r02"
cmp receipt.json "$FRESH/r01/receipt.json" && cmp receipt.json "$FRESH/r02/receipt.json"
```
