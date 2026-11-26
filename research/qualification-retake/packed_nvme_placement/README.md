# Pack C290 integral no NVMe do portátil

**PASS de colocação.** O pack dos 4 608 experts está no mesmo NVMe do GGUF canónico. O fluxo de leitura do USB e uma segunda leitura integral pelo FD do destino produziram o SHA-256 histórico `f17e9fbf6f6aed1ad60ca7da3431c5156a946d2e0bf119722afc1f934cbc6b11`. O pack ocupa 61 096 329 216 B e está em modo de leitura. A instalação local deixou 96 424 669 184 B disponíveis. Esta etapa prepara os offsets reais para a comparação de layouts; o relógio da conversa começa no pedido. [Protocolo](protocol.md) · [Comparação proposta](../phase_fd/integrated/t1_full_pack_service/protocol.md)

A tentativa R01 parou antes de abrir os pesos porque o manifesto aponta para o resumo de readback, cujo digest difere do raw. A correção verifica os dois. R02 foi executada na checkout limpa `7d4c6de1057e609035786ba3c9b1ce3e1b13ce69`. O runner demorou 464,199 s incluindo a admissão C118 de 60 s. A cópia da origem levou 356,601 s, com uma leitura e uma escrita de 61 096 329 216 B cada. A releitura independente no NVMe levou 46,651 s. O cgroup de 1 GiB teve pico de 60 731 392 B, zero swap e zero forwards. Não se mediu energia integrada. [Falha de metadados e correção](repair.md)

A primeira janela passiva de recursos recusou o envelope de 20 GiB por uma diferença de 268 435 456 B. Seis checkouts temporárias, limpas e em detached HEAD foram conservadas no diretório build do projeto no disco externo. Cada caminho anterior em /tmp continua a resolver para a mesma árvore, com HEAD e limpeza verificados. Na segunda janela, o cap disponível foi 22 011 707 392 B. Os raws das duas C55 estão na parte 49. As duas tentativas de colocação estão na parte 50, manifesto `11471692ef9ecd2db53306a2002559211770eba547f5f703eca41012daeb0000`. O recibo privado de sucesso tem SHA-256 `adc58125a13aa286371c127f41bf67b0ed4756e9ec2dc08bd2cb6e7ed754a000`. O manifesto runtime histórico continuou a identificar o inode anterior. A abertura do pack pela DSO da conversa tem uma prova própria. [Autoridade do loader](../packed_nvme_manifest/protocol.md)

Nas 452 amostras ativas, os máximos foram 64.88 °C na CPU, 46.82 °C na GPU e 51.85 °C no NVMe.

Reprodução física na revisão da campanha, com nomes de unidade e saída exclusivos e um destino novo no diretório do GGUF colocado. O recibo do placement original identifica o GGUF e o disco.

```sh
unit=research/qualification-retake/packed_nvme_placement
systemd-run --user --scope --unit="$UNIT" -p MemoryHigh=1G -p MemoryMax=1G \
  -p MemorySwapMax=0 -p RuntimeMaxSec=1800 env LD_LIBRARY_PATH="$MONITOR" \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "$TESY_PYTHON" -IB "$unit/install_pack.py" \
  --commit 7d4c6de1057e609035786ba3c9b1ce3e1b13ce69 --unit "$UNIT" \
  --source "$C283/pack/full-store-v1.bin" --destination "$NEW_PACK" \
  --runtime-manifest "$C283/expert-store-runtime.json" --index "$C290/raw/integral-index.json" \
  --readback "$C290/raw/full-readback.json" --placement "$GGUF_PLACEMENT" \
  --c55 "$C55" --c55-sha256 "$C55_SHA" --new-output-dir "$NEW_RAW"
```
