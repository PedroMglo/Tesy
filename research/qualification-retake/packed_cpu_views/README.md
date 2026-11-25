# Servir os pesos CPU diretamente no destino de leitura do operador

A comparação C293 qualifica o pack como fonte exata de bytes. Ficou aquém do critério de investimento. Cada falta CPU continuava a exigir três chamadas de cópia do staging para os tensores do GGML. A intervenção em avaliação muda o destino do único `pread` e a disposição dos mesmos 40 slots. O routing, a escolha da vítima e os bytes de cada matriz continuam a ser os do target. [Pré-registo](protocol.md) · [Pontos de integração e contraprovas](integration.md)

## Tempo que teria de sair do pedido

O verificador reproduziu os oito recibos nativos da C293, os pares, os contadores e o avaliador original. A coluna da direita responde a uma pergunta contrafactual: quantos segundos adicionais teriam de desaparecer de **cada** braço B para a mediana do ganho em prefill153+decode32 atingir 8%, se o outro caso conservasse as suas medições? O prefixo e a sua duração têm coluna própria no recibo. O avaliador volta a verificar os sinais dos pares e a proteção do outro caso aos dois lados do limiar. [Recibo por braço](distance-r1/receipt.json) · [Reprodução](gate_distance.py)

| Caso fornecido | Ganho do primeiro par A/B | Ganho do segundo par A/B | Redução adicional igual em cada B |
|---|---:|---:|---:|
| Nominal 153+32 | 7,0043% | 7,9408% | 0,101741 s |
| Código 153+32 | 5,2194% | 6,8769% | 0,524421 s |

Se a redução hipotética for proporcional à duração de cada B, os valores de equilíbrio são 0,57005% e 2,07753%. O ensaio C289 de 256 serviços CPU limita o tempo disponível na sua própria agenda. A fração das cópias que atrasava o pedido C293 permanece desconhecida. A resposta com texto livre e os seis tokens/s de M4 têm de ser medidos na receita qualificada. [Limite das cópias C289](../packed_service_bound/README.md) · [Contrato de produto](../protocol.md)

A reprodução das contas foi executada na árvore limpa do commit 1a9ff0d9d67603a78f8224b0b80c32b2de18e0f5. SHA-256 do recibo compacto cc57599e5e71e9e8958e6d1c7f2cf4c180985ab81bd79665af585cc801cbd4f4. O comando requer o raw autêntico C293 e um destino novo.

```sh
python3 -B research/qualification-retake/packed_cpu_views/gate_distance.py \
  --raw-dir "$TESY_C293_RAW" --new-output-dir "$TESY_C293_SAIDA_NOVA"
```
