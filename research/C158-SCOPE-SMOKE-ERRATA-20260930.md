# C158 — smoke e errata de scope

Evidência MEDIDO_NO_TARGET sem modelo: o entrypoint rejeitou scope com sufixo duplicado antes de Popen do modelo. Charge live de 0,303819683 s conservada. decision-effective.json = FAIL_HARNESS_PREMODEL; decision.json original permanece.

Correção causal: congelar nome sem .service, como os runners maduros. Preflight agora rejeita o nome com sufixo antes de systemd-run; seis testes dirigidos do wrapper passam. C159 é tentativa nova. Adicionado gate numérico após OFF para impedir ON se o bridge C140 falhar. Sem alteração de sensores, reserves, cap, thresholds ou tolerâncias.
