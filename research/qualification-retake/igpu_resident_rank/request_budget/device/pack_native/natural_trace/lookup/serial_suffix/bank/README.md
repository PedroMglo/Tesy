# O banco e o sufixo serial ainda excedem os 10 s quando a influência termina na drenagem

Com os pedidos P97 e P106, a mesma recência de 353 chaves e o sufixo L25 até ao retorno, o melhor primeiro final permitido pela hipótese de drenagem é **10,419 e 11,543 s**, respetivamente. O decode cabe em 47/6 s em ambos. Mesmo concedendo também todo o trabalho do sufixo fora das callbacks, ficam **10,314 e 11,437 s**. Estes limites condicionais já oferecem gratuitamente as entregas nas callbacks afetadas, o prefixo do verificador e os custos de rejeição. [Pré-registo](protocol.md) · [Recibo em nanossegundos](receipt.json)

| Pedido e banco | Prefill com propagação até drenar, s | Primeiro final com cobertura direta, s | Primeiro final com propagação até drenar, s | Decode até drenar, s | Saldo para novos custos até primeiro final / no decode, s |
|---|---:|---:|---:|---:|---:|
| P97 · recência | 5,825 | 11,272 | 10,419 | 4,666 | −0,419 / +3,167 |
| P97 · frequência | 5,437 | 11,339 | 10,655 | 5,263 | −0,655 / +2,570 |
| P106 · recência | 6,208 | 12,386 | 11,543 | 4,765 | −1,543 / +3,069 |
| P106 · frequência | 5,785 | 12,452 | 11,773 | 5,389 | −1,773 / +2,444 |

A tabela cobra, em cada linha verificada, desde o primeiro remap de L25 até ao retorno nativo. O prefill é o prompt_ms do mesmo servidor. Antes de créditos, os relógios de prefill, primeiro final e decode foram 9,611/18,326/8,947 s em P97 e 9,925/19,529/9,214 s em P106. O primeiro final é a chegada da primeira peça final ao cliente. A call 46 produziu essa peça, após 44 avaliações de decode. As duas avaliações posteriores só entram no decode. Nenhuma callback da cauda já estava em curso na entrega da peça. A espera pré-stream de 646,428 ms do diagnóstico de P106 conta no primeiro final. Oferecê-la por inteiro ainda deixaria 10,791 s no melhor caso drenado de P106 com sufixo só de callbacks. [Relógios originais](../../../prefill_retention/repeat/README.md)

### Que callbacks permanecem pagas

Em cada traço houve 2 987 callbacks, 2 354 reservas, 23 avaliações AR ordinárias e 11 tentativas de bloco. Cinco tentativas rejeitaram a primeira proposta e cobraram uma linha conhecida do sufixo. Seis confirmaram ambas as propostas e cobraram três linhas cada. Até ao primeiro final contam 10 tentativas e 21 linhas conhecidas. O crivo atribui custo zero ao novo prefixo, inclusive ao cálculo de propostas que se venham a rejeitar. A sua implementação teria de consumir a verba indicada. [Partição causal e orçamento anterior](../README.md)

Nas 23 linhas substituídas, o grafo AR observou 363 reservas CPU antes de L25 e 157 reservas CUDA em L25–35. A recência cobre 54 e 17, respetivamente. A frequência cobre 21 e 24. Portanto, entre as reservas diretamente cobertas nessas linhas, **só 17 ou 24** pertencem a callbacks ainda pagas. Nas avaliações ordinárias e no prefill, a callback mantém-se elegível em qualquer camada. A tabela separa o crédito das callbacks ainda pagas e o crédito comum aos dois mecanismos. Todos os valores são intervalos de parede. As durações nos quatro workers entram apenas no piso residual.

| Pedido e banco | Crédito no prefill, s | Crédito no decode até à peça, s | Crédito na cauda do decode, s | Crédito do banco já retirado pelo corte serial, s |
|---|---:|---:|---:|---:|
| P97 · recência | 3,786 | 1,131 | 0,008 | 0,503 |
| P97 · frequência | 4,175 | 0,507 | 0,035 | 0,226 |
| P106 · recência | 3,717 | 1,149 | 0,006 | 0,494 |
| P106 · frequência | 4,140 | 0,497 | 0,034 | 0,231 |

As chaves dos dois bancos foram seladas em T1 de P106. A aplicação a P97 é retrospetiva e depende da igualdade verificada da entrada, das rotas e da identidade de todas as reservas. Cada pedido conserva os seus preços. Quando se proíbe iniciar propagação em callbacks já gratuitas, os saldos drenados dos dois bancos continuam iguais, ao nanossegundo. Este é um facto sobre a interseção dos journals AR. O efeito de uma drenagem, os hits e a ordem de libertação em B3 continuam por medir. [Cobertura do banco isolado](../../../prefill_retention/request_cost/README.md) · [Cálculo da interseção](score.py)

### O cenário em que a união cabe

Se toda a callback paga depois da primeira influência puder desaparecer, mesmo após o drain, a união cabe nos dois relógios a preço residual zero. A tabela conserva o sufixo até ao retorno. A fração de preço aplica-se só às gerações descobertas que a própria callback reservou e teve de consumir prontas. Para essas gerações, o piso é o maior entre a cadeia READ + três SET e um quarto da soma das cadeias da wave.

| Pedido e banco | Primeiro final a 0× / 0,5× / 1×, s | Prefill / decode a 0,5×, s | Máximo para todos os novos custos ao primeiro final / no decode a 0,5×, s | Máximo uniforme por tentativa a 0,5×, ms |
|---|---:|---:|---:|---:|
| P97 · recência | 5,038 / 8,864 / 12,691 | 5,554 / 3,348 | 1,135882 / 4,485308 | 113,588 |
| P97 · frequência | 5,087 / 8,852 / 12,617 | 5,435 / 3,442 | 1,147915 / 4,391709 | 114,792 |
| P106 · recência | 6,153 / 9,996 / 13,840 | 5,905 / 3,486 | 0,003699 / 4,347022 | 0,370 |
| P106 · frequência | 6,205 / 9,970 / 13,735 | 5,775 / 3,575 | 0,030259 / 4,257890 | 3,026 |

Cobrando só callbacks no sufixo e continuando a 0,5× persistente, o saldo uniforme passa para 124,100/125,303 ms por tentativa em P97 e 10,929/13,585 ms em P106 (recência/frequência, arredondados). As 10 tentativas expostas antes da peça e as 11 do decode têm contabilidade própria. Um custo por tentativa variável pode usar outro perfil temporal, mas os seus custos expostos acumulados têm de caber separadamente nos dois saldos. Os restantes cenários, incluindo os controlos de banco vazio e de todas as chaves, estão nos recibos privados reproduzíveis.

**Decisão.** A cobertura direta é insuficiente e a propagação até drenar também. A envolvente persistente admite margem somente sob preços suficientemente baixos dos jobs descobertos. Em P106, que selou as chaves, a hipótese de preço 0,5× deixa apenas **3,699 ms** (recência) ou **30,259 ms** (frequência) antes do primeiro final para prefixos em bloco, restauração de estado, transferência entre camadas, trabalho desperdiçado e restantes custos novos. Reabrir exige provar a equivalência numérica do grafo e observar, no mesmo target, quanto tempo exposto se recupera depois de um drain, o serviço que persiste e os custos do verificador. Os dados de AR permitem este orçamento condicional, mas deixam desconhecidas as durações do grafo híbrido, a sobreposição CUDA real e as trajetórias de reserva que produzirá.

### Reprodução

Protocolo 32ef2be4. As duas execuções em 78fb1c4c duraram 3,65/3,64 s, com picos RSS de 63 744/63 636 KiB. Reabriram os marginais de custo e de sufixo com os respetivos SHA anteriores e produziram recibos integrais de 162 486 B, idênticos byte a byte, SHA 667700adf58f9b05fbb70884feedd8a0546883909cfee3a403445d8dcd2c955e. Os três testes cobrem hits fora das callbacks pagas, propagação, drain, banco vazio, pisos, arredondamento e relógios sobrepostos. [Testes](test_score.py) · [Compactador independente das paths](compact.py)

```sh
ARC=/mnt/sdisk-ssd-ext/Tesy/outputs/qualification-20261124-nvme-01
for run in 01 02; do
  env LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
    /usr/bin/time -f 'elapsed=%e maxrss_kib=%M' timeout 90 prlimit --as=536870912 --cpu=90 -- \
    python3 -IB score.py --archive "$ARC" --new-output-dir "$FRESH/run$run"
done
python3 -IB compact.py --first "$FRESH/run01/receipt.json" --second "$FRESH/run02/receipt.json" \
  --new-output "$FRESH/compact.json"
```
