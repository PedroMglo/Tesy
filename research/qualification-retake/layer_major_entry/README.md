# O que a entrada de T2 permite ao prefill por camadas

**Reordenar as cinco tiles da chamada de 148 deixa pelo menos 726 leituras de experts nas duas chamadas do prefill.** O próprio segundo pedido R02 usou 1 751 identidades distintas, das quais 852 estavam ausentes dos 1 440 slots primários ao receber o pedido. Das últimas 353 vítimas que T1 tinha guardado, 126 cobriam uma dessas 852 identidades. Restaram 34 primeiras leituras na chamada de 5 e 692 novas identidades na de 148, num total de 462 CPU e 264 CUDA. Cada identidade é um par de camada e expert, com 13 219 200 bytes úteis de matrizes. Ranks repetidos, releituras, alinhamento e SET não entram nessa unidade. [Protocolo](protocol.md) · [Recibo](receipt.json)

O cálculo dá capacidade ilimitada aos dois tiers depois de o pedido chegar e permite qualquer reordenação que preserve as procuras. A primeira utilização de uma identidade ausente das duas fontes ainda exige os seus bytes. Na mesma R02, o mínimo com 40 slots por camada, vítimas escolhidas com conhecimento futuro e saídas livres era de 734 leituras. A diferença entre os dois pisos é oito experts. A execução de atenção, KV, máscara, router e FFN mantém gates próprios. Uma implementação por camadas teria de provar a geometria das tiles e a sobrevivência das ativações e dos estados antes do decode. [Oráculo de 40 slots](../phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/prefill_frontier/oracle/README.md) · [Ordem de execução e dependências](../phase_fd/integrated/tile_pipeline/protocol.md)

## A escolha que teria de acontecer em T1

No sufixo observado do primeiro turno, 524 das 852 identidades em falta chegaram a ser oferecidas como vítimas READY, 338 CPU e 186 CUDA. Mesmo escolhendo o futuro sem erro, com quotas de 263 e 90 ou uma quota global de 353, sobram **499 primeiras leituras**. Das 852, há 328 sem oportunidade de captura no conjunto de vítimas desse sufixo. O banco real cobriu 96 identidades CPU e 30 CUDA. Uma decisão de retenção mais útil pode substituir um membro inútil sem aumentar a capacidade.

| Cenário aos dois preços de pack e aos dois preços de decode | Experts inteiros que cabem no prefill | Identidades úteis que T1 teria de escolher entre 353 | Resultado com seleção perfeita |
|---|---:|---:|---|
| Serviço serial e lacunas conservadas | 372–394 | 458–480 | Faltam 105–127 experts |
| Pipeline ideal de duas tiles | 523–551 | **301–329** | Sobram 24–52 experts |
| Todas as lacunas gratuitas | 591–623 | 229–261 | Sobram 92–124 experts |

O limiar vem de subtrair à população 852 o número de experts que cada combinação comporta. Os 301 correspondem ao caso mais favorável do pipeline; os 329 são necessários para caber nas quatro combinações. A seleção causal teria de cobrir 85,3–93,2% dos seus 353 lugares com identidades úteis distintas. O orçamento usa o tempo até ao primeiro conteúdo final, o preço publicado de 47 saídas e a taxa útil média do pack. A contagem de 726 é independente da duração; as margens temporais dependem das taxas e do preço de decode. Transferências de T1, restauro físico, filas, alterações dos hits de decode e sobreposição real têm custos por identificar. [Medições de transporte e equação conjunta](../phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/prefill_frontier/transport/joint/README.md)

## É possível testar uma regra causal independente?

**NOT_RUN para validação numa conversa independente.** Existe já uma comparação nominal previamente definida de votos do router sobre as vítimas READY. Num segundo processo da mesma conversa cobriu **79** das 852 identidades, contra **126** na recência. O banco dos votos terminou com 280 CPU e 73 CUDA e materializou 10,007 GB em T1, contra 28,329 GB da recência. Ambos ficam abaixo de 301 mesmo concedendo retenção integral durante T2. Reavaliar as duas repetições do mesmo roteiro preserva a evidência nominal. O estudo WRT40 da frequência em P/I visava a expulsão nos 32 passos seguintes. [Comparação de votos já executada](../phase_fd/integrated/t1_local/README.md) · [Política definida antes da medição](../phase_fd/integrated/t1_admission/protocol.md) · [WRT40](../warm_policy/README.md)

Os casos independentes C304 *intervals* e *inventory* abrem o journal de serviço depois da preparação do prefixo e omitem hits individuais nas waves do incremento. O caso de código C294/WRT40 tem os ranks, mas prepara um prefixo de IDs fornecidos em oito chamadas. Falta o histórico das ofertas READY de um primeiro turno natural, seguido de um segundo POST. Dos controladores que efetivamente selam esse prefixo antes do POST, as partes 40 e 63 repetem o nominal. Uma validação independente precisa de uma conversa diferente com quatro conjuntos ligados à mesma sessão: ofertas READY identificadas por geração em T1, 1 440 slots e pendências no corte, seleção recuperável e selada antes do POST, e ranks completos do prefill posterior. O seletor teria de competir com last353 sob o mesmo orçamento, observar só T1 e contar separadamente cópias CPU e GPU→RAM. O limiar absoluto de 301 pertence ao nominal; num pedido diferente há que publicar também o seu universo em falta e orçamento próprio. [Cobertura de C304](../c304_causal_entry/coverage.md) · [Fonte do cliente C294](../../../tools/expert_service_window.cpp) · [Contrato da captura natural](../phase_fd/integrated/t1_capture/capture.md)

## Reprodução e controlos

O verificador exige igualdade entre as uniões de ranks e de demandas em cada tile e camada, quatro IDs distintos por linha, as seis larguras e a poda da camada 35. A conservação do journal liga reserva, leituras, publicação e estado da mesma geração. Quatro mutações independentes foram rejeitadas: digest externo errado do selo, alteração de um registo de T1, duplicação de um dos quatro ranks de T2 e alteração da geração de uma publicação. Nos três últimos casos a mutação foi introduzida em memória depois da verificação da identidade do ficheiro, para exercitar os controlos internos. Nenhum raw foi alterado.

O protocolo foi fixado em `73016251`. Duas reproduções de 0,40 s atingiram 67 916 e 68 192 KiB de RSS. Produziram o mesmo SHA-256, `ff3044886843b8a3cce4b9bbfd58b95e9c20e3fde040bf85c0725325cc0818a5`. [Verificador](screen.py)

```sh
study=research/qualification-retake/layer_major_entry
timeout 10 prlimit --as=201326592 -- python3 -IB "$study/screen.py" \
  --part63 "$ARCHIVE/part-63" --output "$NEW/receipt.json"
sha256sum "$NEW/receipt.json"
```

A reprodução inicial está preservada em `e13326f6` e na parte 79. A cópia de leitura de `protocol.md` perdeu um espaço final de linha após a medição. A reprodução com esta cópia deu SHA-256 `e1c649c0c9dadd0ab4662af2c3f97d2775a167364073538fa6525922fab8770a`; a única diferença entre os dois JSON é o digest do próprio documento. [Manifesto privado](../private_archive/part-79.json)
