# Sobrepor ranks prontos às leituras do pack deixa o decode P106 abaixo de 6 tok/s

**Mesmo antecipando todos os ranks CPU que se tornam utilizáveis na mesma wave, o decode P106 demoraria pelo menos 8,105443 s para 47 saídas, ou 5,79857 tok/s.** Faltam 272,109 ms de ganho independente, antes de cobrar o despacho e a redução. Estender a mesma hipótese aos ranks CUDA baixa o piso para 7,863156 s, ainda 29,823 ms acima de 47/6 s. O resultado usa o preço e a ordem de publicação do pack C291 observados no próprio braço ON de cada conversa. [Recibo por fase, tier e modo](receipt.json) · [Contrato](protocol.md)

| Pedido e contrafactual de decode | Ganho máximo até à primeira peça, 44 avaliações | Ganho máximo no decode, 46 avaliações | Piso do decode | Teto do decode (tok/s)¹ | Margem a 6 tok/s |
|---|---:|---:|---:|---:|---:|
| P97 · CPU | 978,578 ms | 996,669 ms | 7,949957 s | 5,9120 | −116,623 ms |
| P97 · CPU e CUDA | 1 208,865 ms | 1 237,670 ms | 7,708956 s | 6,0968 | +124,378 ms |
| P106 · CPU | 1 085,911 ms | 1 108,404 ms | 8,105443 s | 5,7986 | −272,109 ms |
| P106 · CPU e CUDA | 1 317,725 ms | 1 350,691 ms | 7,863156 s | 5,9772 | −29,823 ms |

¹ Taxa em tok/s = 47 saídas confirmadas / piso do decode no servidor. O P106 observado com instrumentação teve 9,213847 s de decode e 19,528568 s até ao primeiro conteúdo final no cliente. O P97 observado teve 8,946626 e 18,325561 s. O braço independente P106 OFF de produto registou 19,059 s e 5,092 tok/s. O sinal ON/OFF e a trajetória funcional são conhecidos, mas só ON registou os instantes de cada publicação. A margem positiva no decode de P97 é um limite para todo o custo adicional naquele relógio. [Braços de produto](../../../../igpu_resident_rank/request_budget/device/pack_native/full_prefix/session/README.md)

Só antecipar o cálculo em 25 camadas CPU de decode deixa o primeiro conteúdo final P97/P106 em pelo menos **17,346982/18,442658 s**. Mesmo concedendo a intervenção a ambos os tiers **e ao prefill**, os pisos do primeiro final são **15,496262/16,433061 s**. A folga de coordenação para alcançar os dois objetivos por esta via é zero em ambos os pedidos. As oportunidades de prefill e de decode partilham as 44 avaliações com o relógio do primeiro final. As duas últimas avaliações só contribuem para o decode.

### Como interpretar o teto

Dos 1 656 remaps de decode de cada pedido, 546 waves CPU e 229 CUDA tinham pelo menos um rank READY e outro em falta à entrada. A regra progressiva permite também os ranks publicados enquanto se espera pela geração mais lenta. Restringir o início aos já READY na CPU dá no máximo 983,128 ms em P97 e 1 091,613 ms em P106. Para as 46 últimas camadas CUDA de cada decode, a próxima callback já pertence a outra avaliação: o teto concede toda a janela entre a primeira e a última prontidão. Nas demais waves só se credita o menor intervalo entre essa janela e o tempo do regresso do remap à próxima dependência. Esse tempo contém transferências, outros operadores e tarefas do host. Faltam ainda o custo do cálculo que cabe em cada porção, a entrega no consumidor CUDA, a proteção dos buffers e uma redução bit a bit idêntica. [Regra antecedente em GGUF](../README.md)

**Condição para reabrir.** Um efeito independente tem de exceder pelo menos os 272,109 ms do decode CPU P106, ou os 29,823 ms mesmo aceitando as duas colocações, mais os novos custos. Para uma composição com +1 no prefill ou um banco que altere o carry, é preciso demonstrar as publicações remanescentes e o trabalho original ainda exposto no mesmo pedido. Somar os tetos de agendas diferentes atribuiria duas vezes as mesmas janelas. A hipótese de simples sobreposição com estas publicações fica encerrada para os dois objetivos. [Pisos de +1 com a memória transitória do pack](../../../../igpu_resident_rank/request_budget/device/pack_native/natural_trace/release/lookahead2/decode/all_prefill/cpu_only/README.md)

### Reprodução

Protocolo `80c3a288`, verificador e testes `3142197a`. Duas execuções separadas sobre os arquivos 97 e 106, limitadas a uma CPU e 512 MiB de espaço de endereços, duraram 2,18/2,17 s e atingiram 60 988/61 068 KiB de RSS. Ambas reabriram os 1 440 slots à entrada, os 7 012 quartetos oficiais, 2 354 reservas e as 2 987 callbacks, incluindo a correspondência de todos os ranks e gerações das 46 avaliações após o prefill. O resultado foi idêntico byte a byte, SHA-256 `cb19931b91e919049635595de1abc377b88a547aa718c6ffde9e6a8ee47653b1`. Os dados necessários são os journals e os recibos dos clientes. A operação leu zero pesos. [Crivo](screen.py) · [Testes sintéticos](test_screen.py)

```sh
python3 -IB "$UNIT/test_screen.py"
nice -n 10 taskset -c 4 timeout 60 prlimit --as=536870912 --cpu=60 -- \
  python3 -IB "$UNIT/screen.py" --archive "$ARCHIVE" --new-output-dir "$NOVO"
cmp "$NOVO/receipt.json" "$UNIT/receipt.json"
```
