# Biblioteca PFJ1 com o snapshot de política

**PASS de build e fixture CPU.** No ELF candidato, as 4 629 exportações e as entradas dinâmicas de ABI coincidem com o PFJ1 usado na conversa C281. O loader resolveu os 24 objetos de C281 e os 18 de C270. Entre controlo e candidato mudou apenas o SHA-256 de `libllama.so.0`. Esta etapa admite testar a captura na conversa natural. [Pré-registo](build-protocol.md) · [Recibo compacto](build-receipt.json) · [Protocolo do pedido](protocol.md)

| Imagem | SHA-256 |
|---|---|
| C269 original | `347267b2e9cbf920dbf912d6aaf1884e5eff4cccc41c349e93c42bd6403a658f` |
| PFJ1 da conversa de referência | `911b3be5b529d8e07409c12cf600ca9f7f6182f7a397fc6de265e5ea4be254eb` |
| PFJ1 com captura opcional | `a9920fb2a683bd8912ef2a823fdec2aee305f2c09809693c065a76930b7b5d5b` |

O executável CPU usou o mesmo objeto do manager que entrou na biblioteca candidata. Os oito braços reproduziram as decisões e os 6 084 valores inteiros da fixture precedente. As quatro capturas completas, com 48 800 B, coincidiram byte a byte com as da primeira fixture. OFF produziu apenas o PFJ1. Os controlos de corte ausente, duplicado e pendente produziram 128 B cada. Uma segunda ligação ao objeto PFJ1 histórico reproduziu o estado visível de OFF e as decisões sob a mesma variável de ativação. O executável de teste chamou as rotinas de ENTER, RETURN e destruição com o manager C269 genuíno e metadados sintéticos. A produção do ELF e o ensaio CPU não abriram o GGUF nem executaram o servidor. A presença dos contadores no pedido e o custo do observador dependem dos braços físicos OFF e ON. [Cortes e oráculo](../README.md)

O protocolo foi congelado em `68d471b9`. A execução usou a checkout limpa `cbd0540d`, o compilador, os 171 inputs de link e os providers do build qualificado PFJ1. Demorou 5,811 s. O pico do scope foi de 350 949 376 B com limite de 2 GiB e swap zero. O recibo do build original tem SHA-256 `4762116405b6f4bf3fee225be62b4485c01228dccc647febdfd36b8515b5d5bc`. Duas revisões sem compilação reproduziram o recibo compacto `0114a029e5eadd7feacc8b2d1223d6fb1ea14da80c0c5d3c2fef3499d3ee7b0a`.

```sh
unit=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural
python3 -IB "$unit/build_review.py" --build "$BUILD" --new-output-dir "$NEW"
cmp "$unit/build-receipt.json" "$NEW/receipt.json"
```
