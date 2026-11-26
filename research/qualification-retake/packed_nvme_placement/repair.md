# Proveniência dos dois recibos de readback do C290

R01 encerrou em `FAIL_PRESERVED` no teste de autoridades antes da C118, da staging ou de abrir o pack. O recibo, SHA-256 `1674d44827e1ccb882d96db1f87f3539a4fdfcdabe8c1218293e47ddfa0e0a97`, regista `ValueError: original C290 authorities`. O primeiro supervisor comparava o SHA e o caminho do campo `full_readback_result` do manifesto runtime diretamente com o recibo nativo. O C290 emitiu dois documentos com papéis distintos.

- O manifesto referencia `readback-analysis.json`, SHA-256 `21e52d09ee51078cccd53a506bfa5d2f65273a6ceca3c46828f17dc2a0265d36`, com `PASS_INTEGRAL_STORE_BYTES`, SHA do índice, SHA do pack e contagem de 27 648 componentes.
- O testemunho nativo `raw/full-readback.json` tem SHA-256 `54273ebffab1294357932b5c4ee6823be7cb9d9d7420b5582b7294c744b658a0`, `PASS_FULL_CANONICAL_PACK_READBACK`, 27 648 comparações com ambos os FDs em modo direto e 61 073 326 080 B lógicos. O índice congelado contém 4 608 experts.

R02 carrega o resumo pelo caminho do próprio manifesto autenticado e mantém o pin independente do recibo nativo. Confere os quatro hashes dos metadados, o pack e as cardinalidades. O campo público anterior `readback_sha256` continua a identificar o recibo nativo; `readback_analysis_sha256` identifica o resumo. A nova tentativa precisa de identidade e saída novas, sob os limites de recursos e integridade do protocolo original.
