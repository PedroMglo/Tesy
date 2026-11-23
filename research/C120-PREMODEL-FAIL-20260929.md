# C120 — tentativa pré-modelo encerrada

O primeiro braço `c120-p1-control` terminou como `FAIL_HARNESS_PREMODEL` em 2026-09-29 13:49:27 UTC. O SHA passado no comando não era o HEAD de measurement congelado. O gate de identidade impediu o inventário do braço e a criação do processo do modelo; os restantes braços são `NOT_RUN`. Recibo raw local SHA256 `2ec1cf7642dbfe0e6af67181946b4533f77abf8d9739be693ca3e391b0ca388e`.

**Causa e resposta:** erro de operador ao compor o SHA completo. A nova regressão `test_c121_handoff` prova que o caminho de runner produz recibo `FAIL_HARNESS_PREMODEL` e não chama o lançamento nesse caso. C121 usa identidade nova, a mesma época de 12/8 h, novo preflight live e o HEAD efetivo lido do Git. C120 não será retomada.

**Limite:** o smoke sem modelo C120 passou; não houve inferência nem timing do 120B nesta tentativa. C100 e C117 permanecem inalterados. O objetivo e thresholds do screen são conservados em C121.
