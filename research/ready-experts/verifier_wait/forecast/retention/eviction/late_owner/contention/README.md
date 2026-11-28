# O que uma leitura em RAM muda para os outros três workers

**Seguimento no mesmo portátil.** Os quatro workers também beneficiaram de servir duas ou três leituras em RAM. O último miss chegou mais cedo nas duas ordens dos seis níveis de concorrência, em 720 ensaios. Com as taxas individuais qualificadas de dois níveis, o piso ordinário do primeiro final ficou em 9,897 / 10,997 s. A decisão sobre o executor permanece NO_GO. A combinação com outras concessões requer qualificar sobretudo os grupos de duas e quatro leituras em que uma sai do NVMe. [Seis grupos, custos e observação mínima](depth-result.md)

**Decisão para o portátil de Pedro. NO_GO para construir um backend completo com base neste efeito. GO local para o serviço de experts.** Em 28 de novembro, no NVMe interno, servir um expert em RAM fez as três leituras obrigatórias dos outros workers terminar 3,55–3,96 ms mais cedo nas medianas dos quatro contrastes. No segundo turno nominal, a política que capturava vítimas em dois bancos de RAM acertou em 674 reservas no replay. Com os restantes custos conservados, oferecer todas as leituras que chegaram a competir com um hit ainda deixa o primeiro final em **9,415 / 10,534 s**, com provisionamento e captura gratuitos. O melhor pedido HTTP efetivamente observado continua em **17,689 s e 5,357 tok/s**. R0 slots40-persistent continua o controlo, M3 PARTIAL e M4 NOT_MET. [Resultado HTTP](../../../../../../cpu_wave/README.md) · [Composição por processo e por fase](evidence-20261128-r01/victims.json)

## O que chegou mais cedo no portátil

**MEDIDO.** Quatro threads persistentes recebiam sempre as mesmas quatro chaves, com emissão por barreira. D lia as quatro de um descritor O_DIRECT do pack C291. Em H o quarto worker usava os bytes da mesma janela que D tinha preparado e continuava ocupado. Depois da chegada dos três peers e do quarto peso, os workers copiavam as três matrizes MXFP4 de cada expert para quatro destinos CPU. Os hashes foram verificados antes da medição e em cada destino depois do drain. O relógio primário inclui a emissão comum, o despacho pelo sistema, as três leituras e a chegada à barreira. Só o próprio replay do operador tem esta distribuição de arranques. A barreira individual dos quatro READ e o drain têm relógios separados. [Protocolo](protocol.md) · [Leitor](peer.cpp) · [120 ensaios individuais](evidence-20261128-r01/service.txt)

| Camada e expert servido em RAM | Ordem | Mediana dos três peers D / H, ms | Mediana emparelhada H−D, ms | H−D até ao fim das cópias, ms | Rácio mediano do observador ON/OFF na calibração da ordem, % |
|---|---|---:|---:|---:|---:|
| 14, expert 54 | D/H | 17,120 / 13,481 | −3,552 | −3,482 | 100,53 |
| 14, expert 54 | H/D | 17,227 / 13,363 | −3,671 | −3,985 | 101,46 |
| 1, expert 48 | D/H | 17,019 / 13,215 | −3,796 | −3,747 | 99,58 |
| 1, expert 48 | H/D | 17,222 / 13,048 | −3,961 | −3,838 | 98,26 |

O primeiro quarteto vem das duas ablações do 120B em que 94, 29 e 107 ainda estavam a ler quando 54 começou. O segundo foi o primeiro de 55 quartetos comuns aos dois journals com um único hit da política causal de 353 janelas. As reservas 59–62 pediam os experts 47, 3, 10 e 48 da camada 1. Cada linha de custo tem sete pares com observação individual desligada. H adiantou a chegada dos três peers em **28/28 pares**. Os quatro contrastes de calibração passaram o intervalo de 0,97–1,03. Os ensaios incluem ainda dois pares de aquecimento por quarteto. O efeito medido refere-se a duas populações fixas de pesos, na mesma máquina e sessão. [Efeitos individuais, calibração e cópias](evidence-20261128-r01/device.json)

## Até onde chega a política de reter a própria leitura

**TRACE_DERIVED.** As duas observações de T2 têm a mesma trajetória de 2 354 reservas em 48 chamadas. O verificador reconcilia em cada relógio a fila FIFO, geração, worker, READ alinhado, três SET, publicação e último peso dos consumidores que esperaram. Para a política causal de 353 janelas, os hits nas quatro fases são 1, 70, 68 e 1. São as chamadas de 5 e 148, as 44 até à primeira peça final e as duas da cauda. Em P97 a união de parede dos READ omitidos é 1,613 s e o trabalho dos outros workers que lhes é simultâneo soma 3,050 s. Em P106 são 1,583 e 2,974 s. O avaliador conserva o máximo entre o serviço dos quatro workers e o caminho do grafo em cada região. [Atribuição e populações por fase](evidence-20261128-r01/frontier.json)

| Fonte dos hits | Hits em T2 | Reservas nas regiões abrangidas P97 / P106 | Primeiro final dando READ e SET dessas regiões, s P97 / P106 | Decode de 47, s P97 / P106 |
|---|---:|---:|---:|---:|
| Controlo, zero hits | 0 | 0 / 0 | 13,580 / 13,720 | 7,358 / 7,466 |
| Chaves futuras da experiência anterior, apenas na chamada de 148 | 70 | 457 / 457 | 11,959 / 12,153 | 7,358 / 7,466 |
| Frequência causal, 69 | 20 | 119 / 119 | 13,106 / 13,291 | 7,242 / 7,351 |
| Frequência causal, 353 | 140 | 589 / 589 | **11,248 / 11,514** | 6,722 / 6,852 |

As regiões abrangem a chamada, tile e camada de qualquer hit e os peers simultâneos de outras regiões. A tabela oferece ainda as 711 oportunidades CPU e, só em P106, os 646,428 ms do observador do cliente. Sem o último crédito, o valor de 11,514 s é 12,160 s. Um efeito do SSD que persista depois da região ou uma alteração na hora de despacho precisa de outra observação. [Preços com e sem concessões](evidence-20261128-r01/frontier.json)

## Composição com o banco que captura vítimas

**TRACE_DERIVED.** O banco alternativo usa 252 janelas para as camadas CPU e 101 para as CUDA, numa capacidade conjunta de 353. As reservas, a captura da vítima e o slot secundário reproduzem a trajetória registada. Os 674 hits dividem-se em 17, 354, 299 e 4 pelas quatro fases. Custariam ainda 1 971 capturas, ou **26,055 GB de payload** no segundo turno. Há **8,222 GB** de vítimas CUDA cujo conteúdo tem de continuar disponível em RAM. Esses bytes podem vir de uma cópia do primário ou de um backing host preservado, sujeito a ocupação e tempo de vida demonstrados. Os dois cenários abaixo oferecem a captura, pagam os SET e conservam os limites dos retornos. [Pré-registo da composição](victims-protocol.md) · [Política dos dois bancos](../../../../../../layer/prefix/wave/tier-result.md)

| Serviço retirado no replay | Primeiro final com preços ordinários, s P97 / P106 | Primeiro final com créditos CPU e do observador, s P97 / P106 |
|---|---:|---:|
| Apenas o READ dos hits | 12,094 / 13,104 | 11,389 / 11,600 |
| Também a interseção exata de três misses com um hit na mesma região | 11,430 / 12,451 | 10,599 / 10,860 |
| READ inteiro dos peers desses quartetos | 10,919 / 11,964 | 10,023 / 10,314 |
| READ inteiro de qualquer miss simultâneo a um hit | 9,415 / **10,534** | **8,437 / 8,810** |

Só a última amplitude, combinada com os créditos, deixa os dois processos dentro dos dois prazos. Nesse cenário, a redução uniforme mínima da duração integral dos READ dos 671 / 682 peers seria **38,4069% / 47,1311%**. O P106 falha por 1 263 ns a 471 310 ppm e passa por 1 905 ns a 471 311 ppm. No extremo irreal de serviço gratuito, restariam no máximo **1,190 s** para custo adicional exposto aos dois relógios no braço mais exigente. A medição dos dois quartetos dá o preço de uma barreira, que tem outro denominador. Os restantes níveis de concorrência, as capturas e o ganho total no cliente continuam por medir. A próxima fixture deve cronometrar os misses sobreviventes e as capturas nos mesmos grupos causais e comparar com a mesma agenda sem reuso. Uma substituição integral volta a merecer investimento quando se mostrar uma dependência que o atual executor impede de adiantar e houver margem nos dois pedidos naturais. [Cortes, limiares e conservação](evidence-20261128-r01/victims.json)

## Reprodução e limites de produto

Na raiz desta branch, com Python 3, os três comandos reavaliam os resultados sem modelo. `D` designa o diretório deste documento e `E` o recibo novo.

```sh
D=research/ready-experts/verifier_wait/forecast/retention/eviction/late_owner/contention
E="$D/evidence-20261128-r01"
python3 -IB "$D/frontier.py" --check "$E"
python3 -IB "$D/device.py" check "$E"
python3 -IB "$D/victims.py" --service "$E" --check "$E/victims.json"
python3 -IB "$D/test_contention.py"
```

No portátil, os 458 pedidos ao descritor somaram 6 055 624 704 B. A variação de setores lidos do dispositivo inteiro foi igual neste ensaio. Houve 24 verificações iniciais de matrizes e 1 440 nos destinos, 3,064 s de processo leitor, pico de 175 841 280 B no scope e zero swap. Máximos amostrados de 58,875 °C na CPU, 42,03 °C na RTX e 39,85 °C no NVMe. Energia total desconhecida. O hardware do alvo forneceu os pesos originais. Esta unidade teve zero forwards, pedidos HTTP ou testes sustentados. A atribuição no caso de código, a utilidade e os critérios completos de M3/M4 ficam por qualificar para esta intervenção. Os oito ficheiros históricos C317 passaram tamanho e SHA-256. Em C318, os 17,62% nominal e 18,02% código pertencem à via histórica de +15% no decode. [Versões, comandos, hashes, C318 e recursos](evidence-20261128-r01/provenance.json) · [Recibo do arquivo local](evidence-20261128-r01/archive.json)
