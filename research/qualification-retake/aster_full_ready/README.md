# Stock Aster com KV completo

**Preparação sem modelo.** O ELF stock e95426f já aceita as quatro opções necessárias para usar SWA completo e o Jinja datado. Com `--swa-full`, o pin instala para SWA o mesmo número de células que para non-SWA. O servidor imprime em INFO o tamanho e a colocação de cada cache. A trace de inicialização avalia o template efetivo com os kwargs do servidor e mostra o exemplo resultante. O gate verifica a linha da data dentro desse exemplo. Essa amostra distingue a data de C133 da data da estação. [Geometria do stock](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/src/llama-kv-cache-iswa.cpp#L71-L106) · [Exemplo no servidor](https://github.com/ggml-org/llama.cpp/blob/e95426f16982054c379ca7bdc8186996dd22f0fe/tools/server/server-context.cpp#L1695-L1705) · [Protocolo](protocol.md)

O leitor reproduziu a Jinja histórica a partir da fonte stock original, com SHA-256 `0ccef2b31697ba30f891ed18cfc1203b8603f26fc4233faa98839c674819b9eb`. O journal físico histórico compacto passou nos seus próprios marcadores e falhou nas quatro características esperadas do novo perfil: 8192 células SWA, par de buffers CUDA de 288 MiB, anúncio full-size e data vinculada no exemplo. A fixture também rejeitou uma data correta simulada fora do exemplo, um listener alheio, uma topologia de slots incorreta, alteração do template e falha da sonda depois da primeira tentativa. Verificou o modo standalone, o bloqueio antes de placement/VMAs, o callback em andamento, sucesso, erro e contadores. Nenhuma destas verificações lançou o binário de modelo. [Testes do perfil](test_profile.py) · [Referência física compacta](../stock_log/startup-r1/receipt.json)

A autoridade C55 deriva do snapshot e valida política, cap e identidade do modelo/dispositivo. Os formatos do C55 e de FILE_PAGING v3 não fixam um TTL próprio. O supervisor volta a derivar os limites, aceita C55 R5 ou uma nova recolha com o mesmo protocolo e compara o digest do policy e dos samples com o recibo dessa janela. C118 exige os 60 s imediatamente anteriores, amostras no intervalo previsto, idade final entre 0 e 3 s e as condições vivas de potência/pressão/temperatura. Mudança de hardware ou de identidade exige novo inventário. O procedimento não concede novo saldo de campanha. [Política](../../../tools/host_resource_policy.py) · [Verificador C118](../../../tools/c118_start_inventory.py)

### Reprodução

Executar as fixtures sem GPU nem pesos a partir da raiz da checkout.

```sh
python3 -B research/qualification-retake/aster_full_ready/test_profile.py
python3 -B research/qualification-retake/stock_startup/test_startup.py
python3 -B research/qualification-retake/stock_paging/test_paging.py
```

No portátil, a entrada standalone reutiliza o supervisor de stock. A forma abaixo verifica o escopo E10, a política e o GGUF após a transferência, reconstrói e valida o Jinja e verifica os ELFs; termina antes do C118 sem arrancar o servidor. Para um arranque autorizado, usar identidade e destinos novos, remover `--before-inventory-only` e aguardar o recibo e o fecho do filho. O ficheiro de policy deve estar junto de `receipt.json` e `samples.jsonl` da mesma C55.

```sh
systemd-run --user --scope --quiet --collect --unit="$NEW_UNIT" \
  --property=MemoryMax=10737418240 --property=MemoryHigh=10200547328 \
  --property=MemorySwapMax=0 --property=IOAccounting=yes \
  python3 -B research/qualification-retake/aster_full_ready/loader.py \
  --before-inventory-only --expect-head "$MEASUREMENT_COMMIT" \
  --policy "$C55_POLICY" --placement "$VERIFIED_PLACEMENT_RECEIPT" \
  --binary "$STOCK_BUILD/build/bin/llama-server" \
  --build-receipt research/qualification-retake/stock_build/attempt-b/receipt.json \
  --original-jinja "$STOCK_BUILD/source/models/templates/openai-gpt-oss-120b.jinja" \
  --new-raw "$NEW_PRIVATE" --new-output "$NEW_SUMMARY"
```

O perfil standalone pede SIGTERM após confirmar READY, zero pedidos de cliente, topologia, data e VMAs no próprio PID. A entrada da sonda usa o mesmo servidor e só faz os pedidos após essas verificações, mantendo C118, watchdog e telemetria de execução. O journal privado guarda o pedido e a resposta segundo o seu protocolo. O recibo distingue tentativas HTTP, tokens que o cliente pediu ao sampler e os forwards internos do servidor. [Sonda de split no mesmo processo](../aster_split/protocol.md)
