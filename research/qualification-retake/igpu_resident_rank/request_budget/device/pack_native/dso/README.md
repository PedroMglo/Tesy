# Biblioteca privada para observar o pack na C281

**R02 passou a verificação de ligação.** O loader resolveu os 24 providers do servidor C281 e os 18 do cliente C292 ao selecionar a candidata. Os quatro consumidores diretos da libllama são o executável C281, `libllama-server-impl`, `libllama-common` e `libmtmd`. A validação reabriu e confirmou por SHA os 132 logs das listagens, relocações e controlos. A execução durou 14,260 s, com pico de cgroup de 476 041 216 B, swap zero e zero arranques de modelo ou servidor. [Recibo compacto](result.json)

| Variante de libllama C291 | Bytes | SHA-256 |
|---|---:|---|
| Original da conversa com pack | 4 173 608 | `04af70ea943b816769e2c6d62873ded11f00603df6c3be42340b3785aa880819` |
| Relink dos 166 objetos originais | 4 173 656 | `1e21fef6703659839b5c7ce86a5c56e314c7b5fa05e5bbfbe9aea137c20c6bfb` |
| Controlo com duas unidades recompiladas | 4 173 896 | `772740127a1227afae0b0325d0b186f35e1c7e428d6929181019bb8c455b6b25` |
| Candidata com o journal opt-in | 4 199 832 | `9cfa88074e7ca6fa0723f9529aa72b70cea82f2a4bcca53e993733b0f393a0c5` |

R01 exigia a igualdade integral do relink. O GCC histórico era 16.2.1-2 e o CRT local é da revisão 16.2.1-3. O relink mudou apenas as secções `.comment` e `.note.gnu.build-id` e encerrou com FAIL em 0,410 s, antes de qualquer recompilação. R02 voltou a produzir exatamente esse ELF e preservou o original como referência independente. Recompilou as duas unidades com a mesma ferramenta no controlo e na candidata. No controlo, 19 secções carregáveis diferiram do original, além da nota do build-id. A secção `.text` aumentou de 2 352 135 para 2 352 967 B e mudou de SHA. Cada transição acrescentou uma definição C++ fraca. Símbolos fortes e API C preservaram-se. [Protocolo R01](protocol.md) · [Critérios R02](current-toolchain.md)

**O controlo recompilado é obrigatório para a comparação seguinte.** A prova de ligação preserva a seleção dos providers e as relocações. A exatidão no corpus 189+32 e o custo do journal na conversa dependem dos gates numérico e natural. A identidade R02 da medição é `70ce8c21b9fb8a0e1a28f0995c6a845552c6d0d4`. O SHA exterior de R01 é `6526d401ab30ee3db1f72c23608eb2f0987a385c3be295b3aa4967b7fbf360c4` e o de R02 é `cfd616fda7fcdac7aaf6774f9b6d2aac7ea5186a5629fa33eb1bff58a00b34c8`.

### Reproduzir a revisão a partir das duas raízes privadas

```sh
python3 -IB compact.py "$R01" "$R02" | cmp - result.json
```

### Comando físico da compilação R02

Usar a checkout limpa indicada acima em `F` e a raiz C7 original em `C7`. A primeira tentativa usou a checkout `1a100e914554c322e8d7844f4e13b8a8bd8a6e7e`, um destino próprio e omitiu o argumento `--intact-receipt`.

```sh
UNIT=tesy-c291-pfj-dso-r02
S=research/qualification-retake/igpu_resident_rank/request_budget/device/pack_native/dso
systemd-run --user --scope --unit="$UNIT" -p MemoryHigh=2G -p MemoryMax=2G \
  -p MemorySwapMax=0 -p RuntimeMaxSec=360 python3 -IB "$F/$S/build.py" \
  --commit 70ce8c21b9fb8a0e1a28f0995c6a845552c6d0d4 --unit "$UNIT" \
  --backend "$C7/backends/c291-expert-store" \
  --build-root "$C7/results/c283-exact-expert-service-epoch-20261006T194311Z/build/expert-store" \
  --preflight-dir /tmp/tesy-env49-static-r01 \
  --c281-closure /tmp/tesy-c281-pack-link-20261125-r01/receipt.json \
  --c292-closure /tmp/tesy-c292-link-20261125-r01/receipt.json \
  --intact-receipt "$R01/receipt.json" --new-output-dir "$R02"
```

As duas tentativas e os logs do loader ficaram na [parte 93 do arquivo](../../../../../private_archive/part-93.json).
