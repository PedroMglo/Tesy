# C289 — quanto tempo das cópias CPU pode sair da parede?

**FORMAL, condicional aos READ de B.** No microensaio C289, uma intervenção apenas nas cópias CPU cabe num máximo de **0,125044 s** no braço B2 e **0,118885 s** no B3, caso cada leitura conserve a duração observada e a atribuição ao worker. Correspondem a **14,112% e 14,449%** das respetivas janelas CPU. Isso fecha um ganho adicional de 15% no serviço CPU deste B sob essas condições. O ganho realizado por uma arena direta permanece **INCONCLUSIVE**. O GO histórico de A→B continua a descrever a mudança anterior do layout de leitura. [Decisão C289](../../C289-LOSSLESS-SERVICE-INVESTMENT-GO-20261006.md) · [Recibo reproduzido](evidence/receipt.json)

| Braço | CPU parede (s) | CPU soma SET (worker-s) | CPU maior READ acumulado por worker (s) | GPU parede (s) | GPU soma SET (worker-s) |
|---|---:|---:|---:|---:|---:|
| A1 — três leituras por expert | 1,183358 | 0,161747 | 1,025378 | 1,179037 | 0,312060 |
| B2 — uma leitura do pack | 0,886071 | 0,309486 | 0,761027 | 0,985595 | 0,579428 |
| B3 — uma leitura do pack | 0,822816 | 0,361344 | 0,703931 | 0,898256 | 0,555407 |
| A4 — três leituras por expert | 1,201083 | 0,176524 | 1,058246 | 1,200953 | 0,316363 |

**Relógios e trabalho.** O controlador cronometrou CPU e GPU em sequência. Em cada tier despachou 64 grupos de quatro experts, um por worker, com barreira no fim de cada grupo. Foram oito passagens sobre 32 experts por tier. Os braços A fizeram 768 chamadas de leitura por tier e intercalaram cada leitura e SET. Os braços B fizeram 256 leituras de 13 221 888 bytes alinhados e três SET por leitura. Todos entregaram 3 384 115 200 bytes lógicos por tier às três vistas. O relatório soma as durações de chamada READ e SET em cada worker, incluindo bloqueio. O relógio de parede abrange despacho, espera e última barreira. A verificação das 384 componentes e a leitura de controlo dos destinos não entraram nesse relógio. O protocolo não controlou a cache do dispositivo. [Fonte do ensaio no commit medido](https://github.com/PedroMglo/Tesy/blob/dbb8f9220dde64de546deb3b00732e3089bb7263/tools/expert_service_layout.cpp#L89-L116) · [Protocolo](../../../results/c289-lossless-service-resource-qualified-20261006/protocol.json)

**Limite.** Seja `R[g,w]` a duração de READ do worker `w` no grupo `g`. Mantendo as leituras, as suas durações, a atribuição e as barreiras, a nova parede CPU satisfaz `T′ ≥ Σg max_w R[g,w] ≥ max_w Σg R[g,w]`. O termo da direita é o maior READ acumulado de um worker e pode calcular-se com os recibos. Portanto a poupança satisfaz `T − T′ ≤ T − max_w Σg R[g,w]`, mesmo concedendo custo zero às cópias, ao despacho e às barreiras do candidato. Fixando também a duração GPU observada, as paredes seriais CPU+GPU passam a ter pisos de **1,746622 s** e **1,602187 s**. A poupança total de cada sequência fica limitada a **6,681%** e **6,908%**. O caminho crítico do pedido de uma conversa continua por medir.

O contraste A1→B2 tinha ganhos de 25,122% na CPU e 16,407% na GPU. A4→B3 deu 31,494% e 25,205%. Estes pares justapõem o layout original e o pack, ambos com três SET. A ablação para o efeito incremental deve confrontar B com o mesmo pack, destinos, bytes, ordem e número de workers, entregando a leitura diretamente às vistas CPU. Uma alteração da duração de READ ao trocar o destino ou a contenção requer novos tempos. [Análise emparelhada original](../../../results/c289-lossless-service-resource-qualified-20261006/paired-analysis.json)

**Observação mínima em falta.** Os 64 máximos de READ por grupo e por réplica no tier CPU bastam para apertar o piso ideal pelas barreiras. Para atribuir a fração de SET que atrasou a publicação, registar, por grupo e worker, início/fim de READ e SET, despacho e última publicação/libertação da barreira no mesmo relógio, e medir a ablação com o destino alterado. A soma de SET da tabela conta chamadas sobrepostas. O estudo não produz tempos de decode, prefill, C293, de outro armazenamento ou do portátil atual.

**Reprodução.** O verificador autentica tamanho e SHA-256 de cada cópia versionada com o manifesto raw original. A1/B2/B3/A4 ocupam, respetivamente, 2439/2468/2448/2452 bytes. O blob nativo do commit de medição tem SHA-256 `e818d71a6f895d8721f1d30c43e40cf113c70884639123ca643867027789346d`. A fonte atual contém o mesmo sufixo de 5069 bytes que inclui o corpo do probe cronometrado, verificado separadamente. O recibo abaixo consumiu 0,03 s de parede e 19 476 KiB de RSS, com zero novas leituras de pesos e zero forwards. SHA-256 do recibo `c62229fdc1ba415ba342353e2167c9181c00774352c583d0d53da73229890b6e`. [Verificador](verify.py) · [Manifesto C289](../../../results/c289-lossless-service-resource-qualified-20261006/raw-manifest.json)

```sh
python3 -I -B research/qualification-retake/packed_service_bound/verify.py \
  --new-output-dir "$TESY_NOVO_C289_BOUND"
```
