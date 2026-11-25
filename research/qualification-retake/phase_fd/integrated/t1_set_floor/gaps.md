# Quanto da coordenação observada cabe nos 10 s?

**Com as sete lacunas do worker ao preço observado, a melhor seleção de 353 entradas excede 10 s nos dois cenários de READ.** No primeiro, o piso é 10,027167412 s. No segundo, é **10,001387877 s**. O segundo preço tolera até **83,06%** das lacunas na grelha confirmada. Reduzir uniformemente essas durações em 16,94% já faz o piso passar. Uma redução de 16,93% deixa-o acima dos 10 s. O resultado fecha a escolha de conservar o preço integral neste regime. A fração mínima que uma implementação teria inevitavelmente de conservar permanece **DESCONHECIDA**. [Pré-registo](gaps-protocol.md) · [Recibo com numeradores exatos](evidence/gaps.json)

| Preço das 875 primeiras leituras | Piso com lacunas grátis | Piso com lacunas observadas | Limite para K=353 |
|---|---:|---:|---|
| Travessia NVMe 1 | 10,019168047 s | 10,027167412 s | Nenhuma fração entre 0 e 100% satisfaz os 10 s |
| Travessia NVMe 2 | 9,993403747 s | 10,001387877 s | 83,06% dá 9,999999667 s e 83,07% dá 10,000000485 s |

O otimizador recalculou a seleção a cada fração, em 937 callbacks do próprio pedido. Em todos os pontos apresentados o piso de prefill no mesmo testemunho é 8 989 056 000 B, dentro dos orçamentos de 10 690 306 614 B (47 saídas) e de 11 440 306 616 B (46 avaliações). As constantes são os 6,008451991 s fora das callbacks, os SETs locais das 1 894 gerações e o preço externo de cada READ indispensável de uma chave que o oráculo deixou de fora. A seleção concede retenção e pins perfeitos, alias da entrada em RAM e zero tempo para uma eventual entrega suplementar. O preço de coordenação é uniforme em relação às durações específicas de cada geração, incluindo as que teriam hit. [Origem dos preços](nvme.md)

## O que foi cronometrado

Na fonte C269, DISPATCH marca a reivindicação sob mutex, antes de o worker o libertar. READ marca a entrada e o retorno de pread. SET mede a chamada ao backend no host. PUBLISH aparece depois de o worker voltar a adquirir o mutex e mudar o estado da geração. Para cada trabalho, os seis serviços e as sete lacunas somam exatamente PUBLISH−DISPATCH no mesmo worker, slot e geração. O intervalo entre as operações pode conter preparação, instrumentação, desagendamento e aquisição do mutex. A espera do consumidor na barreira fica fora desta conta. [Pontos de registo](../phase-fd-integrated.h) · [Integração no worker](../native.patch)

| Lacuna do worker | Soma nas 1 894 gerações |
|---|---:|
| DISPATCH → começo do primeiro READ | 4,471276 ms |
| Fim do READ 1 → começo do SET 1 | 1,480549 ms |
| Fim do SET 1 → começo do READ 2 | 1,953512 ms |
| Fim do READ 2 → começo do SET 2 | 1,456200 ms |
| Fim do SET 2 → começo do READ 3 | 1,304237 ms |
| Fim do READ 3 → começo do SET 3 | 1,152630 ms |
| Fim do último SET → PUBLISH | 1,920689 ms |

A soma é de **13,739093 ms de worker**. A 100% do preço, o melhor piso de parede sobe 7,999365 ms no primeiro cenário e 7,984130 ms no segundo. A soma por tier e fase encontra-se no recibo. A variação da contenção ou da instrumentação pode mudar estas durações. Mesmo o ponto que passa por cerca de 332 ns no piso depende de escolha omnisciente, de todos os custos gratuitos assumidos e da possibilidade de realizar a agenda. A resolução numérica da bissecção exprime o modelo condicional. A incerteza de uma previsão de latência depende também dos efeitos de execução e de contenção. **M4 permanece NOT_MET.**

## Reprodução

Pré-registo em `a2e12bdd`, código e testes em `13c5f474`. Nove testes passaram. As duas reproduções CPU demoraram 3,89 s cada e usaram 82 480 e 82 796 KiB de RSS máximo. Os recibos de 4 795 B são idênticos byte a byte, SHA-256 `8643cc0346dbbf030f1a0680ffa5e050657ddec9bcff88d5fb5f6d5f5babf2c1`. Sem novo servidor ou leitura dos pesos.

```sh
STUDY=research/qualification-retake/phase_fd/integrated/t1_set_floor
python3 -IB -m unittest discover -s "$STUDY" -p 'test*.py'
timeout 120s prlimit --as=536870912 --cpu=120 --fsize=1048576 -- \
  python3 -IB "$STUDY/gaps.py" --part "$PART40" --nvme-part "$PART38" \
    --model "$MODEL" --inventory "$INVENTORY" --prepared-dir "$PREPARED" \
    --score-dir "$LOCAL_SCORE" --copy 1 --new-output-dir "$NEW"
cmp "$NEW/receipt.json" "$STUDY/evidence/gaps.json"
```

A segunda reprodução seleciona `--copy 2` e os destinos correspondentes da segunda preparação e avaliação local.
