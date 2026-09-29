# C119 — gate de inventário por braço, sem modelo

- **Objetivo:** fechar as contraprovas de C118 antes de qualquer novo screen nominal153.
- **Base:** `4d4bb92e42ea138595f3f2d49d2766545848cd68`, árvore limpa no início. A época física anterior terminou às 12:00 UTC de 29/09; não se iniciou outra.
- **Alternativa:** manter o coletor C118 e confiar apenas na cardinalidade/tempos do validador C117. Rejeitada por aceitar linhas sem observação.
- **Mudança:** o coletor conta a janela a partir da primeira amostra concluída, mede o fim de cada recolha e inclui a identidade do braço. O validador prospetivo verifica conteúdo, todos os NVMe listados, duração/cadência, UTC, frescura, SHA, cap, política e alimentação. Tolerância de arredondamento monotónico: 1 µs; cadência máxima: 1,5 s; idade máxima antes do launch: 3 s.
- **Evidência:** `REPRODUZIDO_MODEL_FREE`. Vinte testes dirigidos passaram; incluem amostra terminal lenta, segundo NVMe quente, série velha, troca de braço/cap, ausência de sensores e mutação de hash. Comando e hashes em `results/c119-inventory-gate-model-free-20260929T1250Z/model-free-tests.json`.
- **Limite:** o caminho builder→freeze→inventário→launch→monitor→recibo ainda não usa este gate. `full_entrypoint=NOT_RUN`, `model_inference=NOT_RUN`; a correção não valida fisicamente o 120B nem promove C117.
- **Falhas preservadas:** C117 continua `FAIL_RESOURCES_OR_EVIDENCE`; C100 continua `NO_GO_CONFIRM`. M3 conserva apenas o âmbito C52b; M4 não foi demonstrado.
- **Próximo gate:** numa época física explicitamente autorizada, integrar o recibo v2 num runner de identidade nova e provar, com subprocessos simulados, que inventário ausente/inválido/velho/de outro braço bloqueia *cada* um dos quatro launches. Só então admitir novo screen nominal153.
