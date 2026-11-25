# Plano das leituras do decode

O candidato precisa de **797 leituras de disco em 632 callbacks** depois da primeira amostra. O plano mantém as 1 656 callbacks das 46 avaliações e as 399 admissões servidas pelo banco, incluindo 1 024 callbacks sem leitura de disco. As 797 leituras têm um serviço de referência de R0 para a mesma chave e no mesmo callback. Cada entrada no ficheiro privado preserva a ordem da reserva, o destino, a geração, os offsets alinhados e úteis e os três SHA-256 esperados. [Recibo](preparation.json) · [Protocolo](protocol.md) · [Limite de parede](../README.md)

| Destino | Callbacks | Sem leituras de disco | Disco | Banco | Bytes pedidos ao GGUF | Bytes pedidos ao pack |
|---|---:|---:|---:|---:|---:|---:|
| CPU | 1 150 | 720 | 541 | 330 | 7 158 231 040 | 7 153 041 408 |
| CUDA0 | 506 | 304 | 256 | 69 | 3 387 215 872 | 3 384 803 328 |

O consumidor lê `plan.json` privado, `groups` por step, posição, call, tile, camada, wave e tier. Filtra `jobs` por `source == "disk"` preservando o ordinal original, inclusive nos grupos que ficam vazios. Cada job possui `components` na ordem gate/down/up com role, SHA-256, intervalo útil do GGUF, offset e tamanho alinhados e offset relativo no pack. A janela do pack começa em `pack_offset` e tem `pack_bytes` bytes. O custo de SET da geração homóloga de R0 fica em `r0_same_site_set_ns`. As 227 novas admissões por banco têm preços de referência nulos e permanecem sem medição temporal. Combinar futuras leituras com o SET do mesmo job antes de calcular o piso do grupo. O plano volta a produzir exatamente 0,522063311 s com READ gratuito, 5,191159642 s a 0,8× e 6,359376443 s a 1× no interior das callbacks.

Congelamento `cfca4628339fa729d11b56104d6a5037b0c9830f`. As duas reproduções independentes geraram o plano privado de 1 244 124 B com SHA-256 `aed09397a16ed706365d73e0d2535427528476b41d66e3d5e43ad90da345d79a` e o recibo `faa756041cab0f35b12ed06a91058e54b389582839820ea265dad69c52b19993`, ambos idênticos byte a byte. Custo da preparação de 0,77 s / 85 180 KiB e 0,74 s / 84 732 KiB. Os dados lidos foram índices, receipts, journal e snapshot. GGUF e pack ficaram fechados.

```sh
P=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/replay/decode_clock/transport
A=/mnt/sdisk-ssd-ext/Tesy/outputs/qualification-20261124-nvme-01/part-63
C7=/mnt/sdisk-ssd-ext/Tesy/repo/c7-native-placement-screen-20260927-1117utc/results
OPENBLAS_NUM_THREADS=1 python3 -IB "$P/prepare.py" \
  --family "$A/tesy-policy-natural-physical-20261125-r02" \
  --index "$C7/c290-integral-lossless-store-20261006/raw/integral-index.json" \
  --placement /tmp/tesy-full-pack-placement-20261125-r02/receipt.json \
  --new-output-dir "$NOVO"
```
