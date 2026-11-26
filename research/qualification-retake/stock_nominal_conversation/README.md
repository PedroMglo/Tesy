# Conversa nominal C281 no derivado stock E20

**NO_GO para este perfil no protocolo nominal.** O servidor aceitou o pedido inicial de 2 043 IDs e começou a emitir raciocínio, mas não entregou conteúdo final até ao limite de **180 s**. Foram aceites **0 de 1 pedidos iniciados**. O segundo turno exige a resposta válida do primeiro e ficou **NOT_RUN**. O controlo R0 no mesmo portátil e NVMe já completara 2 de 2 turnos. A paridade numérica deste derivado na posição 15 da fixture C110 mantém-se; a qualificação da conversa continua M3 PARTIAL e M4 NOT_MET. [Protocolo congelado](protocol.md) · [Recibo físico](physical-r01/receipt.json) · [R0/NVMe](../nvme_conversation/README.md) · [Comparação dos logits](../stock_server_logits/README.md)

| Pedido e métrica | R0/NVMe C281 | Derivado stock ON E20 |
|---|---:|---:|
| T1, entrada oficial | 2 043 novos IDs | Mesmos 2 043 IDs e mesmos bytes renderizados |
| T1, primeiro conteúdo final / resposta validada | 84,448 / 84,914 s | Primeiro final censurado a 180 s, nenhuma conclusão validável |
| T1, prefill / decode do servidor | 64,443 / 20,438 s, 78 tokens de saída | Sem estatísticas terminais atribuíveis ao pedido |
| T2, histórico / incremento | 2 044 IDs em cache e 153 novos | NOT_RUN |
| T2, primeiro final / decode / validação | 21,443 s / 4,523 tok/s / 21,735 s | NOT_RUN para as métricas nominais de 10 s e 6 tok/s |

## Pedido e evidência de censura

O modelo original MXFP4 de 120B estava no NVMe interno. O servidor usou o pin `e95426f16982054c379ca7bdc8186996dd22f0fe`, a biblioteca derivada com prefault desativado, CUDA com 161 slots em 36 camadas, b256/ub32, um slot de conversa, contexto e ambas as KV completos de 8192. O supervisor verificou no PID que o observador de logits estava ausente. O cliente confirmou o render e todos os IDs de T1 com a referência C281 antes de enviar a geração com data `2026-10-05`, esforço medium, temperatura zero, seed 42 e limite de 256 tokens. Este limite é o número pedido como máximo. O stream foi interrompido antes de publicar uma contagem terminal de tokens gerados. [Autoridade das entradas](../nominal_stock_input/README.md) · [Cliente](client.py)

O HTTP 200 chegou aos 0,0081 s do relógio monotónico do cliente. O journal preservou 102 linhas SSE — 51 separadores vazios, três comentários e 48 linhas de dados JSON. Uma anunciou o papel de assistente aos 102,8730 s. As outras **47** continham deltas de raciocínio não vazios, do primeiro aos **107,1711 s** ao último aos **178,5789 s**. A contagem de fragmentos não mede tokens. Houve **zero deltas de conteúdo final**, zero eventos com `finish_reason` terminal, zero registos de uso terminal e nenhum marcador `[DONE]`. O temporizador do cliente expirou aos 180,0005 s. O supervisor confirmou `WATCHDOG_T1_REQUEST_TIMEOUT`, encerrou o filho com SIGKILL (retorno −9) e recolheu-o. O scope ficou inativo. A falha de produto observada é a ausência de conclusão dentro do orçamento. [Recibo com hashes dos oito raws](physical-r01/receipt.json) · [Arquivo privado selado, parte 12](../private_archive/part-12.json)

O último progresso de prompt no log indicava 1 792 tokens, fração 0,88 e 83,69 s no relógio do slot. Essa linha conta tokens de lotes anteriores cujo processamento já retornou com sucesso no host. É emitida antes de encher o lote seguinte. O servidor sincroniza explicitamente a view de saída e pode ter trabalho assíncrono pendente nas intermédias. O último tempo impresso não é uma medição do prefill completo, e os relógios da resposta acima provêm do cliente. [Impressão do progresso](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/tools/server/server-context.cpp#L739-L750) · [Ponto de emissão](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/tools/server/server-context.cpp#L4371-L4374) · [Sincronização e contagem](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/tools/server/server-context.cpp#L5132-L5178)

## Custos, proveniência e limites

| Fase ou recurso | Observação |
|---|---:|
| C55 novo, ambos os caps admissíveis | 62 amostras em 61,029 s, 23 GiB e reserva 2 GiB |
| Pré-check sem modelo / C118 imediatamente antes do arranque | 0,1303 s / 60,1597 s, 61 amostras |
| Lançamento até READY / tempo do processo incluindo encerramento / supervisor incluindo C118 | 6,3891 / 186,8804 / 247,4319 s |
| Pico do cgroup / high / limite, swap | 20 939 546 624 B / 19,5 GiB / 20 GiB, zero swap |
| Eventos de memória high / max / OOM | 578 185 / 0 / 0 |
| Máximo amostrado de VRAM / número de amostras do processo | 4 386 MiB / 273 |
| Máximos amostrados de temperatura CPU / GPU / NVMe | 76,75 / 55,91 / 55,85 °C |
| PSI full avg10 máximo, anfitrião / cgroup | 5,64% / 6,36% |
| Leituras físicas do namespace / io.stat atribuído ao cgroup | 311 732 076 544 / 311 523 958 784 B (290,323 / 290,129 GiB) |
| Raw total / orçamento | 1 018 939 B / 64 MiB |

As leituras abrangem arranque, pedido e encerramento. O namespace inclui o restante tráfego no dispositivo. A energia da unidade ficou desconhecida. Os valores amostrados de potência da GPU durante o braço variaram entre 2,77 e 33,42 W. A paragem ocorreu pelo relógio do pedido. Com uma execução e candidatos que diferem em backend, cache e momento de medição, estes dados não isolam a causa temporal nem antecipam o desempenho de T2. [Janela C55](c55-r01/receipt.json) · [Pré-check](precheck-r01/receipt.json) · [Arranque e pedido](physical-r01/receipt.json)

A medição usou a checkout limpa `831122558e6a19ed25e845a3ff586188c52ce292`, árvore `2e41c1802076d759649c06f29d5f5098bf6bc90f`. Os recibos de pré-check e físico foram preservados byte a byte, SHA-256 `47fa80122f90cd38a3f9ec0f58f6af72181da50bcd2cb2550c985b7b5bfa5378` e `935ecfcd4ae6aa0d68d77e3d1b15cd85c1348cf1169373ab3dabfd33ef42cd16`. O resumo C55 referencia o digest do recibo integral privado. [Supervisor](profile.py) · [Parte 12 do arquivo](../private_archive/part-12.json)

## Reprodução

Os testes abaixo verificam os contratos sem modelo. O procedimento físico histórico usa `NO_REPLACE` para raws e recibos. Os resultados e o prazo absoluto de 25 de novembro, 05:34 UTC, ficaram congelados no supervisor. Uma campanha posterior requer `NOVA_IDENTIDADE`, protocolo próprio, hipótese material que possa alterar o custo da conclusão de T1 e nova admissão. Os resultados atuais mantêm R0 como controlo operacional.

```sh
python3 -B research/qualification-retake/stock_nominal_conversation/test_profile.py
python3 -B research/qualification-retake/stock_nominal_conversation/test_client.py
```

O comando documenta a entrada física de R01. Executado na checkout acima, recebeu o raw privado da conversa R0 em `HISTORY`, o build B stock, overlay e recibo da fixture CPU, os dois recibos originais da família de logits e das entradas, a C55 posterior e a colocação NVMe autenticada. O pré-check usou `--before-inventory-only` numa unidade e saídas exclusivas. Uma execução com modelo requer que o pré-check passe e usa outros dois destinos exclusivos.

```sh
systemd-run --user --scope --quiet --collect --unit="$NEW_UNIT" \
  --property=MemoryMax=21474836480 --property=MemoryHigh=20937965568 \
  --property=MemorySwapMax=0 --property=IOAccounting=yes --property=RuntimeMaxSec=650s \
  python3 -B research/qualification-retake/stock_nominal_conversation/profile.py \
  --expect-head 831122558e6a19ed25e845a3ff586188c52ce292 \
  --policy "$C55_POLICY" --placement "$NVME_PLACEMENT_RECEIPT" \
  --binary "$STOCK/build/bin/llama-server" \
  --build-receipt research/qualification-retake/stock_build/attempt-b/receipt.json \
  --original-jinja "$STOCK/source/models/templates/openai-gpt-oss-120b.jinja" \
  --overlay-root "$OVERLAY" --attribution-receipt "$TINY_CPU_ATTRIBUTION_RECEIPT" \
  --family-receipt "$ORIGINAL_NUMERIC_FAMILY_RECEIPT" --input-receipt "$ORIGINAL_C281_INPUT_RECEIPT" \
  --history "$HISTORY" --new-raw "$NEW_PRIVATE_RAW" --new-output "$NEW_REPORT"
```
