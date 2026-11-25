# Uma captura correta pode acompanhar um FFN errado?

**MEDIDO na CPU C269. Sim.** A fixture atrasou o consumidor da geração antiga. Com a vista de ordenação da wave original ou uma espera explícita pela conclusão do grafo, os 32 valores do FFN coincidiram bitwise com a referência da geração antiga. Ao retirar a vista e concluir a sobrescrita antes da leitura, os 32 valores passaram a coincidir bitwise com a geração nova. Os três braços capturaram os mesmos bytes antigos e deixaram os mesmos bytes novos no slot. Portanto, conferir apenas o banco e o destino final deixaria escapar esta falha. **PASS_CPU_OPERATOR_ONLY. CUDA NOT_RUN.** [Protocolo em 246ce04d](protocol.md) · [Recibo nativo](evidence/cpu.json)

| Braço | Condição para o worker substituir o slot | Geração lida pelo FFN | SHA-256 da saída completa |
|---|---|---|---|
| ORIGINAL | Sinal do observador após ler a vista escalar da wave anterior | Geração antiga | `1e1e6519…1b6981f` |
| EVENT | Sinal explícito após compute e sincronização do backend | Geração antiga | `1e1e6519…1b6981f` |
| BROKEN | Observador apenas dos IDs, com o leitor atrasado até ao último SET | Geração nova | `6ebc5310…9ef77537` |

O grafo usa as três projeções GGML MUL_MAT_ID, SwiGLU OAI, máscara e soma em ordem. São pesos sintéticos MXFP4 de 32×32, quatro slots, um token, um rank ativo e três de parking. O valor máximo absoluto do erro frente ao cálculo escalar independente foi 2,24×10⁻⁷ na geração antiga e 5,60×10⁻⁶ na nova, para o limite fixado de 10⁻⁴. A captura verificou 1 632 B da vítima. A verificação final cobriu 6 528 B de todos os slots e papéis. Os dois golds foram computados em processos isolados. A CPU executou dois agentes com sinais limitados por prazo e um único backend de grafo. Os streams físicos da GPU, a travessia CUDA→CPU do scheduler, a reserva dentro do manager, o custo e a geometria de produto ficam por qualificar. [Arestas no source e teste físico proposto](../t1_manager_bank/cuda-consumers.md)

## Reprodução

O primeiro comando é portátil, usa a biblioteca padrão Python e cobre permutações de cinco eventos, adulteração de bytes, troca de gerações e saída não finita. O segundo é uma integração **opt-in no portátil**. Requer o backend C269 local, os headers do commit `d0ebfbcc6c8f456bc1083027c1b08075a32824d8`, `g++-15` e dois DSOs autenticados do mapa C269, ggml-base e ggml-cpu. Cada filho verifica os providers, as 3 projeções e a ausência das bibliotecas CUDA nas suas VMAs. O supervisor guarda o executável, os logs, os bytes e os hashes em destino exclusivo e preserva falhas.

```sh
unit=research/qualification-retake/phase_fd/integrated/t1_manager_cuda
python3 -IB "$unit/test_check.py"
python3 -IB "$unit/run.py" --backend "$C269" --map "$STATIC_MAP" --new-output-dir "$NOVO"
```

R01 fechou em 25 de novembro de 2026, com 0,715 s de compilação e 0,017 s para os cinco processos. O pico do filho, incluindo o compilador, foi 191 692 KiB. O recibo SHA-256 `ef013d60b5899dd9f8513518ab9f742af8ee8423072f12b7c34e9e88901e1dce` identifica a fonte nativa, o verificador, o compilador, os providers, o binário e os dois golds. Zero modelos e zero atividade da fixture na GPU. O sinal de avanço exige agora comprovar no dispositivo que a conclusão da última leitura da vítima precede a primeira escrita da geração nova.
