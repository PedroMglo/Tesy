# Um banco renovável e um novo leitor justificam outro backend?

**NO_GO para construir um backend dedicado a partir desta combinação no portátil.** Os quatro workers já conseguem começar pelos experts residentes no backend atual. O limite decisivo apareceu no prefill. Todas as 436 leituras antecipadas que o primeiro cálculo dava gratuitamente tinham um consumidor obrigatório dentro da própria camada e tile. Ao cobrar os respetivos bytes, mesmo uma seleção futura perfeita, com retenção ilimitada durante T2 a partir do banco inicial de recência, tem um piso de **10,031013326 s** no primeiro final de P106 com o grafo observado e o cliente integral. Os 10 s ainda exigem mudar pelo menos um desses custos ou a informação disponível ao produtor. O resultado pertence a este perfil de máquina e a esta conversa. [Prova de dependência](deadlines.py) · [Recibo compacto](evidence/decision.json) · [Operador exato no backend atual](../layer/README.md)

**MEDIDO.** Uma fila nativa `io_uring` reduziu o tempo de serviço das duas waves de quatro leituras nos 14 pares do portátil. As reduções medianas emparelhadas foram **4,85% e 5,55%**. Nos pedidos de uma única leitura, o sinal variou com a ordem. Na melhor política causal testada, com SET pago, a redução uniforme de READ necessária seria **40,8610%** com o grafo observado ou **26,8818%** concedendo integralmente o tempo após as waves vazias compatíveis na CPU. Esse limiar serve para selecionar o próximo teste de serviço. A medição física cobriu quatro grupos da conversa, sem forward. R0 `slots40-persistent` continua operacional. O melhor turno natural já medido com pack no NVMe interno teve **18,313 s** até ao primeiro final, **18,565 s** até à validação e **5,361 tok/s**. M3 PARTIAL e M4 NOT_MET. [Contrato da medição de leitura](reader/protocol.md) · [Dois controlos de produto trace-OFF](../../qualification-retake/packed_nvme_manifest/server_profile/conversation/ordens.md)

## O que tinha de chegar antes de a camada terminar

**TRACE_DERIVED.** P97 e P106 são processos independentes com a mesma conversa, mesmos 2 044 tokens reutilizados, 153 adicionais, 47 IDs e 48 chamadas. O replay verificou 1 440 donos iniciais no primário, 2 354 reservas, um READ e três SET por geração, 2 354 publicações e drain. O primário R0, os quatro workers, o target, o retorno 5+148, ub32 e a ordem de redução são os mesmos. As 44 avaliações de decode anteriores ao primeiro final contam nos dois relógios. As duas últimas só entram no decode. A execução observada e os exteriores de cada relógio vêm dos recibos originais. [Fronteira de cliente e fases](../protocol.md)

| Local da primeira procura da geração | Prefill | Decode antes do primeiro final | Decode final |
|---|---:|---:|---:|
| Na wave que fez a reserva | 827 | 1 067 | 24 |
| Em wave posterior da mesma camada e tile | 436 | 0 | 0 |
| Em região posterior ou nunca observada | 0 | 0 | 0 |

A identificação usa camada, slot, geração e expert. Cada READ/SET está ligado à sua reserva e publicação. A primeira procura tem de receber essa publicação até ao retorno do seu remap. As 436 antecipações ocorreram depois de a camada ter entrado e foram usadas antes de sair. O limite oferece quatro trabalhadores ideais, sobreposição com grafo dentro das duas camadas vizinhas e aquisição gratuita das vítimas. Mantém os preços individuais dos dois journals. Uma previsão que inicie o READ antes de conhecer a rota desta camada altera a premissa.

## Quatro relógios por escolha

**Projeções com SET pago**, a menos que a linha indique acesso direto gratuito. A combinação «despacho CPU» concede o intervalo integral entre a saída de uma wave vazia elegível e o callback seguinte, inclusive a parte que se gasta na camada seguinte. Nos dois traces o grafo admite 711 das 739 waves vazias em CPU. Os intervalos concedidos somam 1,216 s em P97 e 1,323 s em P106. O avaliador retira cada intervalo uma vez e recalcula o caminho crítico. Os tempos apresentados conservam todo o cliente.

| Política e grafo | Primeiro final P97, s | Primeiro final P106, s | Decode P97, s | Decode P106, s |
|---|---:|---:|---:|---:|
| Observado com pack, trace-ON | 18,326 | 19,529 | 8,947 | 9,214 |
| Recência causal, grafo observado | 12,405 | 13,394 | 6,312 | 6,474 |
| Frequência causal, grafo observado | 12,053 | 13,055 | 6,402 | 6,556 |
| Frequência causal + despacho CPU | 11,345 | 12,192 | 6,402 | 6,556 |
| 353 lugares escolhidos com o futuro, grafo observado | 9,842 | 10,855 | 4,605 | 4,773 |
| Mesma escolha + despacho CPU | 9,109 | **9,966** | 4,605 | 4,773 |
| Retenção ilimitada durante T2, grafo observado, acesso direto gratuito | 8,940 | **10,031** | 3,758 | 4,001 |

O limite de decode é 47/6 s para estes 47 IDs. A concessão separada de 646,428 ms anteriores ao stream de P106 continua insuficiente para as duas políticas causais. Mesmo com hits diretos e despacho CPU, ficam em 11,808 s por recência e **11,442 s por frequência** em P106. No cenário retrospetivo combinado com SET pago, a margem do relógio integral é **33 857 551 ns**. Essa margem teria de pagar a parte que realmente fica em cada lacuna, captura, contenção, coordenação e cleanup adicionais. A testemunha ocupa até 353 lugares, exige 1 015 capturas somando **13 417 488 000 B** de payload lógico e promove 1 185 janelas. Desconhecem-se a fração das cópias que se poderia sobrepor e o tráfego DRAM real dessa agenda. A otimização conhecia as duas observações de T2 e dá exclusivamente um resultado de viabilidade da ocupação. [Agenda e verificação dos lugares](intervals.py) · [Atribuição dos custos ao grafo](composition.md)

**REPRODUZIDO.** A reanálise pós-C320 verificou tamanho e SHA-256 dos oito ficheiros originais C317. Nos oito braços C318, os cortes condicionais do decode para a via histórica de +15% continuam a ser 17,62% no nominal e 18,02% em código. A decisão do staging aprendido é NO_GO. Os 26,88% desta unidade incidem sobre a duração de READ nas faltas restantes do turno natural. A consolidação do clone completo verificou 45 heads e 7 253 caminhos históricos. [Reanálise, clocks e proteção dos pares C318](../../post-c320/README.md)

**Como mudou a decisão.** Antes de restaurar os 436 consumidores, o banco fixo reproduziu os tempos do #52 ao ns. O banco de recência parte das 353 vítimas seladas, das quais 48 já estão no primário. Promover antes de demitir levou de 327 a 604 hits totais em T2. O acumulador causal de frequência, treinado nas 5 727 reservas verificadas em T1 e atualizado só com a reserva presente, deu 691. No cálculo inicial, a seleção por preço ainda excedia 10 s em 11,116 ms com acesso direto. Vinte e quatro trocas produziram 9,967 s com SET e sem desconto de cliente. A mesma seleção passou a **11,290 s** quando foram repostas as dependências. Cada etapa tem protocolo próprio, dados e resultado auditáveis. [Primeira concessão](protocol.md) · [Pré-registo dos intervalos](intervals.md) · [Teste dos consumidores](deadlines.md)

## O que mudou no leitor físico

O pack C290 no NVMe interno foi aberto uma vez com O_DIRECT e apenas para leitura. PRE usa quatro threads persistentes com `pread`. RING entrega o lote a uma fila persistente de profundidade quatro e recolhe uma conclusão por janela. Os dois usam os mesmos buffers alinhados e pré-tocados e fazem drain no fim de cada grupo. As waves dos quartetos foram as primeiras elegíveis das camadas 0 e 25 da primeira tile da chamada de 148. Os pedidos isolados vieram das camadas 1 e 29 do primeiro decode. Estes nomes de destino descrevem a origem do pedido. A fronteira medida termina nos pesos disponíveis em RAM. As duas paridades foram verificadas antes dos 28 braços de custo e todas as janelas foram verificadas também após a cronometragem. [Seleção e digests de origem](reader/prepare.py) · [Implementação](reader/native.cpp)

| Ordem em cada um dos sete pares | Grupos | PRE mediana, ms | RING mediana, ms | PRE − RING emparelhado, ms | Variação emparelhada do tempo | RING mais rápido |
|---|---|---:|---:|---:|---:|---:|
| PRE/RING | 2 × 4 leituras | 38,211 | 36,212 | +1,857 | −4,85% | 7/7 |
| RING/PRE | 2 × 4 leituras | 38,438 | 36,248 | +2,123 | −5,55% | 7/7 |
| PRE/RING | 2 × 1 leitura | 9,280 | 9,137 | +0,043 | −0,47% | 5/7 |
| RING/PRE | 2 × 1 leitura | 9,332 | 9,212 | −0,013 | +0,15% | 3/7 |

As medianas de diferenças e razões são calculadas dentro dos pares. A assinatura do RPM Fedora dos cabeçalhos 2.13-2 foi verificada. Compilação local em diretório isolado, SHA-256 do ELF `b977bdd17d156147ba695393690f6f93b390ea923ccbe00c2e4942c5db7ef304`. Na árvore limpa `0cfcf6a40daf479cc42a2832c480c7cfa2c8fe89` / `d3a439fd6aad203e1a149d75430f1feb2d299dc2`, o filho levou 3,110 s. Houve 3 966 566 400 B pedidos e 900 verificações SHA-256 de componentes, incluindo paridade e os dois blocos. O contador do dispositivo inteiro avançou 3 966 910 464 B de leitura e 8 192 B de escrita durante a janela. O descritor do processo só admitia leitura. O scope atingiu 101 126 144 B de RAM, zero swap e zero eventos de pressão nos limites. Nos cinco pontos de telemetria do scope, em AC/performance, os máximos foram 55,75 °C na CPU, 42,97 °C na RTX 4060 Laptop e 38,85 °C no NVMe. A janela C55 anterior durou 60,006 s. Zero execução GPU, zero pedidos 120B e energia por braço desconhecida. A análise dos traces consumiu respetivamente 3,16, 2,73, 5,72 e 6,68 s, com RSS máximo de 153 636 KiB. [Supervisor físico e cálculo emparelhado](reader/physical.py)

## Implicação para a arquitetura

**NO_GO para um novo backend sustentado por estes mecanismos no perfil atual.** O operador exato e o leitor cabem no backend existente. O último pode interessar em lotes de quatro. Compor mecanismos exige temporizar os mesmos bytes e o trabalho crítico que sobra. O limite de 26,8818% aplica-se a uma redução uniforme nos READ restantes, com o SET pago e a maior concessão de grafo. A melhora local nas waves de quatro mantém valor como componente. A qualificação de produto requer ainda histórico inédito, proteção de código, contexto, utilização sustentada, recursos e validadores completos na mesma receita.

**Condição para reabrir.** A intervenção seguinte deve mudar quais os pesos que precisam de chegar durante uma região crítica ou quando podem começar a chegar. Uma via concreta é mudar as vítimas do primário com conhecimento das cópias já disponíveis. Essa política já deu ganho em quatro waves, seleccionadas entre casos favoráveis. A comparação seguinte precisa das gerações novas e das que desapareceram por prazo de consumo no pedido inteiro, com os custos das leituras adicionais e proteção de decode. Uma redução em CPU ou transporte só entra no prazo de uma região onde esses custos estejam expostos. [Medição de composição do layout e das vítimas](../../qualification-retake/phase_fd/integrated/t1_primary_layout/README.md) · [Cobertura das waves medidas](../../qualification-retake/phase_fd/integrated/t1_full_workload/README.md)

**Literatura revista em 27 de novembro.** O estudo de Zhang mostra que a granularidade do replay pode inverter a ordem de políticas de cache. Aqui a ordem de retenção vem do mutex e a unidade de custo termina no consumidor da rota. O trabalho de Bacon e colegas mede transferências reais de OLMoE-1B-7B na L40S e encontra uma diferença entre a escolha com informação futura e as regras baseadas no passado. Não se transferem daí fatores de velocidade para o NVMe do portátil. O SSD-LLaMA junta io_uring, staging assíncrono e compressão opcional numa RTX 5090. O nosso par separa a API de submissão com os mesmos bytes e a mesma concorrência máxima. A questão científica continua a ser a contribuição causal no pedido de uma pessoa. [Zhang, §§2, 4 e 7](https://arxiv.org/html/2608.07911v1) · [Bacon et al., método e apêndice C](https://arxiv.org/html/2611.15842v1) · [SSD-LLaMA, §§4.1 e 5](https://arxiv.org/html/2609.18110v1)

## Reprodução

A base imediata de investigação foi `a87c1d9a` no #52, sobre o #51. A main observada era `293f5b18`. Os quatro cálculos foram executados nos commits limpos `7afb92d7`, `f605b064`, `2add9b1b` e `b4565f33`, após os pré-registos `0d4c1df5`, `3004ecd9`, `8c1fe5d8` e `2a73fcd2`. O pré-registo físico é `4dc5c72a`. O arquivo privado exclusivo `outputs/ready-renewal-20261127-01` tem 32 ficheiros e 403 031 B antes do manifesto. SHA-256 do manifesto `b95c0b9632cb700ecf55922084af96818e93f34640e103af8f99ac470472f864`. Os PFJ continuam no arquivo privado de qualificação. O resultado público reproduz-se com Python e a biblioteca padrão.

```sh
s=research/ready-experts/renewal
out=$(mktemp -d)
python3 -IB "$s/replay.py" --archive "$TESY_ARCHIVE" --verify "$s/evidence/initial-selection.json.gz" --new-output-dir "$out/renewal"
python3 -IB "$s/intervals.py" --archive "$TESY_ARCHIVE" --control "$out/renewal/receipt.json" --new-output-dir "$out/intervals"
python3 -IB "$s/composition.py" --archive "$TESY_ARCHIVE" --intervals "$out/intervals" --placement "$TESY_RENEWAL_ARCHIVE/placement" --new-output-dir "$out/composition"
python3 -IB "$s/deadlines.py" --archive "$TESY_ARCHIVE" --intervals "$out/intervals" --composition "$out/composition" --placement "$TESY_RENEWAL_ARCHIVE/placement" --new-output-dir "$out/deadlines"
python3 -IB "$s/compact.py" --archive "$TESY_RENEWAL_ARCHIVE" --new-output-dir "$out/public"
cmp "$s/evidence/decision.json" "$out/public/decision.json"
```

Para rever a atribuição sem a busca, acrescentar `--verify "$TESY_RENEWAL_ARCHIVE/composition/witness.json"` ou o ficheiro homólogo de `deadlines` ao respetivo programa. Para repetir o teste do leitor na árvore física, executar `reader/build.py --rpm RPM --new-output-dir BUILD`, depois `reader/prepare.py --archive ARCHIVE --manifest MANIFEST_C291_R02 --new-output-dir PLAN` e `research/qualification-retake/nvme_admission/window.py --nvme-model GGUF --new-output-dir C55`. Conferir PASS e SHA-256 de cada `receipt.json`. Executar `reader/physical.py` com `--build`, `--plan`, `--c55`, os três argumentos `--…-sha256` correspondentes e um novo `--new-output-dir`, num `systemd-run --user --scope --slice=app.slice` com MemoryHigh=MemoryMax=256M, MemorySwapMax=0, TasksMax=64 e RuntimeMaxSec=120. O ficheiro de decisão inclui todos os tempos emparelhados, os cortes por política e os hashes dos recibos. O launcher operacional e o modelo original conservam os pins existentes.
