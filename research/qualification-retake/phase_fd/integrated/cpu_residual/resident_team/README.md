# Colocação dos oito threads na tile residente C266

**A equipa mista B terminou 4,009 e 3,584 ms antes da equipa de oito Zen 5c A nos dois blocos inversos. A comparação entre B e o escalonamento normal R ficou inconclusiva.** Em R−B o primeiro bloco deu −0,169 ms e o segundo +0,172 ms. Neste portátil, fixar a equipa em B não demonstrou um ganho face à política que o servidor já usa. A comparação cobre uma tile de 32 posições da camada CPU0, com os cinco experts residentes. [Protocolo anterior à medição](protocol.md) · [Medições de cada percurso e contrastes](receipt.json)

| Ordem dos processos | Colocação dos oito threads | Parede OFF, mediana (ms) | Parede ON, mediana (ms) |
|---|---|---:|---:|
| Controlo independente | R, escalonador Linux | 18,053 | — |
| 1 | R | 16,941 | 16,897 |
| 2 | A, núcleos 4–11 | 21,119 | 21,833 |
| 3 | B, núcleos 0–7 | 17,110 | 16,929 |
| 4 | B | 17,284 | 17,515 |
| 5 | A | 20,868 | 20,114 |
| 6 | R | 17,457 | 17,692 |

O relógio principal vai de `ggml_backend_sched_graph_compute` ao retorno da sincronização. Cada processo marcado fez OFF, ON, ON, OFF. Os seis rácios ON/OFF ficaram entre 0,964 e 1,034. As duas medianas OFF de R foram 0,938 e 0,967 da mediana dos quatro percursos do executável original. Ambos os controlos passaram a banda de 15% pré-registada. O controlo independente usou o mesmo grafo e a biblioteca histórica sem interposição do observador de nós. [Critérios do revisor](grade.py)

## Que trabalho ficou identificado?

Nas quatro observações ON de R, a união do tempo de parede dentro dos 24 despachos `MUL_MAT_ID` ocupou **14,130–14,942 ms**. A wave ativa respondeu por 13,400–14,134 ms. As outras sete juntas ocuparam 0,731–0,820 ms. A parede do grafo completo nos mesmos percursos foi 16,800–17,694 ms. Somar os intervalos dos oito threads dá 112,749–119,196 ms por grafo, incluindo espera concorrente. A união de intervalos serve para comparar com a duração do grafo. [Valores dos quatro controlos e restantes braços](receipt.json)

As marcas `CLOCK_MONOTONIC` delimitam o retorno do hook de dispatch até à chegada à barreira original entre nós. Incluem a coordenação interna da MMID e o curto percurso do dispatch. A espera na barreira entre nós fica fora da união. Nos 12 percursos ON houve 24 nós × 8 threads por percurso e **zero pares com CPUs distintas nos 2 304 intervalos**. Só se observaram as duas extremidades. Frequência, L3, espera pelos pares e migrações com regresso à mesma CPU permanecem causas indistinguíveis. [Observador e endereços da PLT](observe.c)

## Exatidão, residência e recursos

Em cada um dos sete processos, o percurso frio deu cinco leituras O_DIRECT (66 109 440 B devolvidos) e 15 SET (66 096 000 B de pesos). Seguiram-se um aquecimento e quatro percursos medidos da mesma tile. Cada um dos 35 percursos residentes produziu cinco hits, uma wave ativa em oito callbacks, **zero leituras ao FD do pack e zero SET de pesos**. Os 40 slots conservaram identidade, geração, estado e claim. Os quatro workers C291 conservaram os TIDs e as máscaras herdadas até ao join. Os 92 160 F32 de cada um dos 42 percursos foram finitos e iguais bit a bit ao gold externo. A publicação da ativação, IDs e mistura precedeu cada relógio. [Grafo e fronteiras](execute.inc) · [Referência C266](../../../../cpu0_suffix/README.md)

A família R01 completou os sete processos em 62,449 s, incluindo C118 com 61 amostras em 60,174 s. O cgroup E4 registou pico de 277 196 800 B, zero swap e zero filhos após o fecho. A execução tinha alimentação AC, perfil performance e C55 R03 válida. O pré-teste do build exercitou 24 MMID sintéticas com o DSO real, 0 marcas OFF e 192 ON. Os testes de falsificação cobriram sete falhas de marcação. A família física terminou na primeira identidade. [Teste do observador](test_observe.py) · [Recibo de revisão](receipt.json)

A atribuição ao pedido natural continua a exigir as marcas dentro dos seus próprios grafos, com as oito lanes, e o cruzamento com os períodos exteriores aos remaps. As medidas desta tile deixam por identificar essa fração, a colocação efetiva do servidor e qualquer mudança quando há serviço de disco ou CUDA concorrente. [Antecedente e orçamento do pedido](../README.md)

## Reprodução

Freeze de build e medição `85dcc0529cd0f6e67ef22a81009cb5b0332fa517`. O cliente usa o manager C291 `c89c88b342054223e3f27a17fbfd0954803147ac` e os providers CPU/base de C269. A revisão reabre comprovativos, executáveis, ambos os providers, o gold das sete tiles e os 28 percursos medidos. [Revisor](review.py)

```sh
Q=research/qualification-retake/phase_fd/integrated/cpu_residual/resident_team
FROZEN=/mnt/sdisk-ssd-ext/Tesy/repo/build/tesy-resident-team-frozen-20261125-r01
BUILD=/tmp/tesy-resident-team-build-20261125-r01
FAMILY=/var/tmp/tesy-resident-team-physical-20261125-r01
LIBS=/mnt/sdisk-ssd-ext/Tesy/repo/c7-native-placement-screen-20260927-1117utc/backends/c269-layer-last-use/build-c269-cuda/bin
python3 -IB "$FROZEN/$Q/build.py" --old-build /tmp/tesy-cpu0-suffix-build-20261125-r01 \
  --libs "$LIBS" --new-output-dir "$BUILD"
LD_LIBRARY_PATH=/tmp/tesy-packed-service-nvml-20261125-r01/lib python3 -IB "$FROZEN/$Q/profile.py" \
  --checkout "$FROZEN" --expect-head 85dcc0529cd0f6e67ef22a81009cb5b0332fa517 \
  --unit tesy-resident-team-20261125-r01 --build-dir "$BUILD" \
  --build-sha256 b1b5ab6207574b507e652ea06e99361704e40761f9db9a1c8f93b01b1c96ed1e \
  --input-dir /var/tmp/tesy-packed-real-layer-input-20261125-r01 \
  --input-sha256 a3a6028b45719ee0a1c63f689a2e6896b5a401ee394d5aa9d3188d98e72dc269 \
  --libs "$LIBS" --c55-receipt /var/tmp/tesy-real-tile-c55-20261125-r03/receipt.json \
  --c55-sha256 52cfcdd0ce2b457fe50c7eb15b47831b8b25a20ed4a712d1904426af0cdfbfcf \
  --new-output-dir "$FAMILY"
python3 -IB "$Q/review.py" --physical "$FAMILY" --build "$BUILD" \
  --physical-sha256 eeffcfe458a380ef88c574465998205fdf63df9a393f065912f8916ffc762a6f \
  --new-output-dir "$NEW_REVIEW"
cmp "$NEW_REVIEW/receipt.json" "$Q/receipt.json"
```

Os caminhos de build e medição acima identificam os destinos exclusivos usados. A reprodução offline usa as suas cópias completas em arquivo e um destino novo para a revisão. O compacto reproduzido tem SHA-256 `8c0992de9632e06941d7e868e954a9dad84faa7cc5c0ee969ca89768cbd38e8e`.

A revisão em `/tmp/tesy-resident-team-archive-review-20261125-r01` usou o build e a família da parte 122. Produziu um compacto idêntico byte a byte ao da primeira revisão. O manifesto privado cobre 55 ficheiros e 8 646 495 B, SHA-256 `162f61f780fabfd854ec1c7d4519a7dcb9690ed511138f06b74cd2fb65724eda`. [Recibo do arquivo](../../../../private_archive/part-122.json)
