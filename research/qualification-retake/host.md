# Estado da receita R0 no portátil

**MEDIDO em 24 de novembro de 2026. Inferência NOT_RUN.** O ficheiro GGUF corresponde integralmente ao SHA-256 do GPT-OSS-120B MXFP4 congelado. O perfil R0 continua sem condições para uma execução comparável de M3/M4 neste inventário. O binário e as sete bibliotecas do backend coincidem com os hashes congelados. O código local do backend está limpo na revisão d0ebfbcc6c8f456bc1083027c1b08075a32824d8, numa checkout histórica. O launcher da main procura a sua própria árvore relativa. [Recibo medido](host-evidence/receipt.json) · [Launcher operacional](../../tools/c143_slots40_optin.py)

| Objeto | Observação | Consequência |
|---|---|---|
| Conteúdo do modelo | 63 387 346 208 bytes, SHA-256 `582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d` | A cópia tem os bytes originais. A identidade histórica de dispositivo/inode já diverge. |
| Armazenamento | ext4, transporte USB. O predicado congelado C55 recusou o backing do GGUF. | O pedido qualificado precisa de uma colocação NVMe com proveniência nova. |
| RAM antes da leitura | 61 amostras, 60,000 s. Mínimo disponível 16 681 951 232 B, reserva 2 147 483 648 B e teto calculado 14 495 514 624 B (13,5 GiB). | Ao cap de 20 GiB faltaram pelo menos 6,5 GiB nessa janela. Uma nova admissão teria de repetir a observação de recursos. |
| Bibliotecas do sistema | libstdc++ e libgomp divergiram. Os caminhos congelados de libgcc_s e libcuda estavam ausentes. | A auditoria ELF posterior identificou os 23 objetos que o linker seleciona. Os quatro objetos dessas famílias têm digest diferente. [Seleção do linker](elf-evidence/receipt.json) |
| CPU e GPU | Ryzen AI 9 HX 370, RTX 4060 Laptop, 8 188 MiB, dos quais 2 MiB usados no instante de consulta. Driver 620.70.06, GPU a 49,48 °C. | Inventário de entrada. Recursos, energia e térmicas durante geração continuam por medir. |

A única leitura integral usou O_DIRECT, SHA-256, comparação do stat antes/depois e relação com o caminho no final. Durou 144,810 s. A ferramenta completa ocupou 206,88 s, com 29 584 KiB máximos de RSS. A unidade consumiu zero forwards e zero downloads de pesos. A energia da leitura ficou DESCONHECIDA. A política de recursos, o estado térmico, alimentação, swap, processos concorrentes e filesystem de todas as saídas voltam a ser medidos no preflight completo de uma campanha futura. [Protocolo](protocol.md) · [Inventário C55](../../tools/c55_inventory.py)

Reprodução opcional, para uma nova leitura integral expressamente orçamentada. A terceira entrada é a raiz da checkout onde se pretende operar o launcher.

```sh
python3 -B research/qualification-retake/host_readiness.py \
  --model "$TESY_MODEL" --backend "$TESY_HISTORICAL_BACKEND" \
  --operational-checkout "$TESY_CHECKOUT" --new-output-dir "$NEW_HOST_AUDIT"
```

Digest do protocolo `19bbb51bae496b32e4570145a00a1b1ca83ad217c8afa95aa19024a02afb1484`. Digest do auditor executado `799e6e0baa87227e951bccc59ad9c41452a86465414d963212b4b1944eb30b82`. Digest do recibo `c20e5301620468ca4d9c79a3ead7dff8e944179bab9bce7527057627f57b951e`.

## Decisão de colocação

Em 24 de novembro, depois da verificação integral de conteúdo, Pedro decidiu conservar o GGUF apenas no SSD USB por agora. O próprio ficheiro medido continua a ser a cópia de trabalho. Enquanto esta colocação vigorar, o critério de armazenamento do protocolo R0 impede a sua campanha de qualificação física, mesmo que surja uma janela admissível de RAM. Uma experiência que estude a configuração USB precisa de identidade e comparador próprios.
