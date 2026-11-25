# Serviço de experts na conversa real de dois turnos

**NO_GO para resolver o nominal apenas com reuso frio ou com a eliminação da espera de prefill, nas condições abaixo.** O R0 no NVMe interno concluiu os dois turnos e reutilizou o histórico da própria resposta. No braço OFF o primeiro conteúdo final do segundo turno chegou em **20,274 s**, a resposta válida em **20,544 s** e o decode atingiu **4,752 tok/s**. Os alvos são 10 s e 6 tok/s. Houve um servidor por braço, quatro workers, 40 slots por camada, ub32, contexto 8192 e o mesmo GPT-OSS-120B MXFP4 original. M3 continua **PARTIAL** e M4 **NOT_MET**. [Proveniência e braços](conversation/README.md) · [Controlo independente](../../nvme_conversation/postupdate/physical-result.md)

| Braço e turno | Cache + novos IDs | Gerados | Prefill (s) | Decode (s) | Primeiro final (s) | Resposta válida (s) | Decode (tok/s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| OFF T1 | 0 + 2043 | 78 | 61,615 | 19,687 | 80,886 | 81,312 | 3,962 |
| ON T1 | 0 + 2043 | 78 | 62,046 | 19,842 | 81,473 | 81,900 | 3,931 |
| OFF T2 | 2044 + 153 | 47 | 10,640 | 9,891 | 20,274 | 20,544 | 4,752 |
| ON T2 | 2044 + 153 | 47 | 10,746 | 10,004 | 20,486 | 20,761 | 4,698 |

Nos dois braços coincidiram os 78 e os 47 IDs amostrados, o EOG, as entradas e o conteúdo dos canais. As quatro razões temporais ON/OFF de T2 ficaram entre 1,0099 e 1,0115, dentro da banda prospetiva de 0,85 a 1,15. Este par permite interpretar o diagnóstico no seu próprio regime. Uma estimativa da variabilidade e uma qualificação de neutralidade temporal precisariam de repetições. A GPU chegou a 6848 MiB, o cgroup a 15 745 503 232 B e o swap dos processos foi zero.

## O que atrasou a resposta

O journal ON abriu no limite de T2 e fechou depois da reunião dos quatro workers. Reconciliou 55 354 eventos, 2 354 reservas, despachos e publicações, 7 062 leituras e cópias, 325 itens de fila ignorados e 2 987 pares de barreiras. Na entrada havia 1 440 slots identificados e zero em LOADING. As 48 chamadas externas compreendiam 5+148 e 46 avaliações unitárias. A chamada de 148 manteve as tiles 32+32+32+32+20. A última camada respeitou a poda das saídas. As três componentes de cada geração chegaram ao slot correto e o FD foi ligado por dispositivo e inode ao GGUF da campanha. O perfil identifica o retorno ao pread e o payload na cópia. Os contadores de barramento e tráfego físico do NVMe não foram instrumentados nesta família.

| Prefill ON | Gerações novas | Bytes devolvidos pelo FD | Duração nativa | Última publicação exigida após entrar na espera |
|---|---:|---:|---:|---|
| Chamada de 5 | 51 | 674 832 384 | 0,485 s | 29 primeiras procuras, 0,336 s até publicar |
| Chamada de 148 | 1212 | 16 036 343 808 | 10,257 s | 130 primeiras procuras, 4,048 s, e 88 recargas, 2,623 s até publicar |

Nas duas chamadas, 16 711 176 192 B regressaram do FD e 16 695 849 600 B foram copiados. Nenhuma leitura originada nessas duas chamadas terminou depois da fronteira final do prefill. A união das leituras nas chamadas foi 7,474 s, das cópias 0,975 s e da espera 7,017 s. Os intervalos sobrepõem-se. Até ao primeiro conteúdo final, incluindo a parte de decode que ocorreu antes desse instante, houve 14,488 s de callbacks de remap. Reduzir essas callbacks por uma fração uniforme exigiria pelo menos **72,37%** para o primeiro final e **28,41%** para o decode. As figuras ligam a última dependência ao consumidor bloqueado; a poupança efetiva de a eliminar requer uma nova medição.

Nas 46 avaliações autoregressivas pós-primeiro, as leituras para camadas CPU devolveram 10.400 GB e as das camadas CUDA 4.036 GB. Por cada um dos 47 tokens confirmados de T2, isso representa 221.28 MB e 85.86 MB de serviço de ficheiro, respetivamente. Os SET com destino CUDA entregaram 85.78 MB de payload por token confirmado no decode. Incluindo o prefill, o serviço total do FD foi de 662.70 MB por token confirmado de T2. Estes números usam MB decimais. [Contagens por fase e dispositivo](conversation/evidence/receipt.json)

## Limites que mudam a escolha de arquitetura

- **Só prefill.** Mesmo concedendo gratuitamente 7,028 s de remap no prefill, restariam 3,718 s. O orçamento no próprio ON, dando todo o crédito de levar o decode a 6 tok/s antes do primeiro final, é 2,431 s no contrato de 47 tokens. Com a relaxação de 46 avaliações AR, sobe para 2,597 s. Faltariam, respetivamente, 1,287 e 1,121 s. A chamada inicial de cinco só ocupou 0,485 s. O prefixo conhecido antes de chegar a nova mensagem comporta no máximo oito posições adicionais. [Prova de prefixo](../../predictable_turn/README.md) · [Âmbito do limite](wait_bound.md)
- **Restaurar o primário.** Com entrada autêntica e cache ilimitada, 852 experts ausentes exigiram pelo menos 11,263 GB de payload no prefill. A relaxação offline de 40 slots por camada elevou o piso a 859 cargas e 11,355 GB. Exigir também os 1 440 residentes observados à entrada do primeiro decode elevou-o a **894 cargas e 11,818 GB**. Mesmo creditando os 3,383 ms entre as chamadas para restaurar o estado a 4,5 GB/s, faltariam 864 MB no denominador contratual e 114 MB na relaxação de 46. Foram concedidos gratuitamente pins, identidades físicas, gerações, coordenação e outros custos de reposição. Estes são limites de volume com a taxa assumida. [Corte do primeiro decode](retorno.md)
- **Eliminar recargas no pedido inteiro.** Para a primeira procura ainda fria, conservar apenas os jobs de demanda que partiram da própria wave e as suas três leituras seriadas. Foram 875 até ao primeiro conteúdo final. Com quatro workers, o piso do seu serviço foi **6,232 s** às durações observadas, além de **5,997 s** de trabalho fora das callbacks. Atribuir custo zero a preloads, hits, cópias, coordenação e restantes leituras ainda deixaria **12,228 s**. A 80% da duração dos preads daria **10,982 s**. O cenário só deixa margem abaixo de **64,24%** da duração de serviço observada, mantendo o restante fixo. A contenção está incluída nas durações dos preads. Uma medição direta dos mesmos grupos com quatro leitores no NVMe pode distinguir esse custo. [Modelo condicional da primeira procura](mandatory.md) · [Recibo com ambos os denominadores](nominal-r01/limits.json)

A compilação reproduziu os dois objetos e a DSO de controlo byte a byte. A biblioteca experimental passou seis sondas de fornecedor, a fixture de proveniência com leituras curtas, e o C270 OFF/ON no portátil com 1500 payloads e cinco vetores completos de logits em cada braço. A primeira fixture falhou antes do build por comparar duas codificações diferentes do manifesto. Na preparação da conversa, R01 não teve capacidade, R02 usou um destino externo recusado, R03 passou e a primeira tentativa de ON encontrou a porta ocupada antes de lançar o modelo. A tentativa ON seguinte fez o seu próprio C118 e usou o OFF conservado. As identidades, saídas e falhas estão no arquivo privado. [Fixture](native-results.md) · [C270 e VMA](profile/README.md) · [Recibos e conversas](conversation/README.md)

## Reprodução offline

Usar os dois raws da conversa e o manifesto ON da parte 37. O caminho do modelo permite verificar a identidade do FD com stat. O script de limites não lê os pesos. Os resultados públicos contêm contagens e hashes; os raws com o texto e os IDs ficam no portátil.

```sh
python3 -IB research/qualification-retake/phase_fd/integrated/limits.py \
  --on-dir "$TESY_PFJ_ON" --on-sha256 78c3a5bb34353d2b880b14bfa80634cd06dfe465beec529446206a8728af3f43 \
  --off-dir "$TESY_PFJ_OFF" --off-sha256 171e90939e42a55ce51b196224ecc2bb008cc7408205eae7e961d09759cdfc5f \
  --archive-manifest "$TESY_PART37/manifest.json" --archive-sha256 4c7715c643684b4b7b058fb20d0daea19c95d766a0a60aad43ce2cb29d9c2239 \
  --model "$TESY_120B_NVME" --new-output-dir "$TESY_NEW_OUTPUT"
```

O par do cliente usou a revisão 91251633. O verificador de limites partiu de f939264b. O estado independente de C317/C318 e as decisões sobre os workers permanecem no [índice pós-C320](../../../post-c320/README.md). Uma observação parcial pode ser inventariada com incomplete.py antes do diagnóstico. Só o audit completo de um journal selado admite a análise temporal.

Mantendo a agenda primária original, uma L2 fria ideal precisa de servir 1 051 chaves distintas no prefill, incluindo 199 que R0 tinha inicialmente e expulsou antes de voltar a pedi-las. Os 13,893 GB desse piso excedem os dois orçamentos. A LRU de 353 slots só acertaria em 48 das 1 091 cargas de decode. Para que uma L2 morna mude o critério contratual de volume, T1 teria de deixar pelo menos 224 chaves úteis, com custo e retenção pagos. A hipótese de melhorar isoladamente a afinidade da CPU também fica aquém no cenário medido. [Cache secundária](host_cache/README.md) · [Topologia e limite do cálculo CPU](cpu_residual/README.md)

## Teste físico das primeiras procuras

Duas travessias independentes leram no NVMe as três componentes originais das mesmas 875 primeiras procuras em 441 waves, com quatro leitores, sem modelo de inferência ou GPU. Os 2625 hashes dos payloads coincidiram. Cada travessia devolveu **11 577 561 088 B**. O piso de serviço com as durações de leitura medidas foi **5,743/5,692 s** e a soma das paredes até à barreira **6,051/5,996 s**, para **4,003 s** disponíveis no cenário do primeiro conteúdo final. O melhor piso excedeu o orçamento em **1,688 s**. Esta medição elimina a explicação de que bastaria remover a carga concorrente do grafo, mantendo as libertações das mesmas waves e o restante do pedido fixo. Em cada travessia o cgroup ficou abaixo de 176 MiB. [Plano autenticado](cold_read_fixture/plan.md) · [Protocolo de serviço físico](cold_read_fixture/protocol.md)

Se as waves de uma camada puderem começar logo na primeira callback que expõe os ranks e sobrepor as leituras a todo o cálculo entre as suas waves, os pisos ainda dão 10,123/10,073 s. Uma libertação anterior aos ranks deixa só margem matemática. A alternativa de capturar chaves durante T1 é distinta da hipótese de as reler no intervalo curto depois da resposta. [Limites de antecipação por camada](router_release/README.md)

## O que a cache recebe e quando

Com 353 entradas, começar a guardar vítimas READY no início de T2 acerta em **280 das 1 091 cargas de decode**. Começar a guardar publicações acerta em 48. A primeira regra preserva também alguns experts que já estavam residentes no primário quando chegou o pedido. Em ambos os casos ficam por servir os 875 primeiros jobs que sustentam o piso temporal. Mesmo no cenário com as leituras a 0,8×, o primeiro conteúdo final ficaria em pelo menos **10,982 s**. Na cache de vítimas, os hits exigiriam ainda copiar 20,252 GB de vítimas CPU e 9,650 GB de vítimas CUDA para a RAM no decurso de T2. Estes bytes são lógicos e o simulador atribuiu custo temporal zero às cópias. [Comparação por fase e por capacidade](t2_victims/README.md)

Se a cache receber as suas primeiras entradas de T1 e aceitar publicações durante T2, o oráculo exige **247 chaves** previamente escolhidas para passar simultaneamente os pisos de tempo e de volume a 1×. Com 239, o melhor piso é 10,104 s. Com 353, desce para 8,913 s, ainda antes de pagar a preparação e a entrega. Para a cache de vítimas, há um piso de volume diferente porque ela pode salvar até 199 residentes iniciais sem preparação durante T1. O custo real da escolha depende dos bytes que o primeiro turno chega a disponibilizar. [Mesma seleção nos dois pisos](warm_oracle/joint.md) · [Definição da observação causal](t1_capture/capture.md)

**Resultado da captura iniciada em T1.** O cliente selou as últimas vítimas antes de enviar o segundo pedido. Dentro das 1 698 chaves disponíveis, guardar as últimas 353 ou escolher 353 pelos votos reais do router fica aquém mesmo com READ 20% mais rápidos e sobrevivência perfeita até à primeira procura. A escolha com conhecimento do futuro tem um piso de **10,129 s** quando se cobram os 5 682 SET dos workers com os preços do próprio processo. No denominador M4, também há um certificado independente para qualquer banco de 353 entradas mantido fixo durante T2. [Seleções causais e falha histórica explicada](t1_local/README.md) · [Prova do banco fixo](t1_static_bank/README.md) · [Os dois relógios do mesmo pedido](t1_decode_gate/README.md)

Quando o preço de cada READ vem das duas travessias autónomas do NVMe, o piso com os SETs é **10,019168 s / 9,993404 s**. Ao conservar ainda o tempo observado no worker entre despacho, leituras, SETs e publicação, os pisos passam a **10,027167 s / 10,001388 s**. O segundo preço ultrapassa o alvo por apenas 1,388 ms. Esta pequena diferença distingue uma hipótese sobre custos da demonstração de um limite físico. Os controlos conservam os quatro workers, o instante de libertação de cada wave e o restante do pedido. [Preços físicos por componente](t1_set_floor/nvme.md) · [Custo de coordenação e limiar de reabertura](t1_set_floor/gaps.md)
