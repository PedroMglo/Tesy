# Cinco experts reais da camada CPU0

**MEDIDO. GO para medir a espera pela publicação.** Nos três braços, o FFN da camada CPU0 produziu os mesmos 92 160 F32 finitos que a referência independente C266 confirmou contra as capturas C265 e C270. A janela cobre as posições 32 a 63 da captura de 153. O router calculou 19 584 logits antes do bias, 19 584 depois, 612 IDs top-4 e 612 pesos na ordem do target. Os três braços concordaram em bits nas quatro comparações. [Protocolo congelado](protocol.md) · [Recibo físico](physical-r01/receipt.json)

| Braço no portátil | Origem dos pesos para MUL_MAT_ID | Leituras e bytes pedidos ao pack | SET e bytes entregues por SET | Saída FFN igual |
|---|---|---:|---:|---:|
| DENSE, C291 original | Três tensores contíguos independentes | 5 · 66 109 440 B | 15 · 66 096 000 B | 92 160/92 160 |
| STAGED, mesmo patch e arena que DIRECT | Três vistas por slot, cópia após a leitura | 5 · 66 109 440 B | 15 · 66 096 000 B | 92 160/92 160 |
| DIRECT | As mesmas três vistas, com a leitura no endereço da primeira | 5 · 66 109 440 B | 0 · 0 B | 92 160/92 160 |

Cada processo começou com 40 slots vazios e utilizou quatro workers. Os cinco experts 45, 49, 57, 60 e 98 cobriram sete tuplos distintos de ranks. O observador confirmou a identidade dos operandos nas 24 projeções das oito waves, das quais uma serviu ranks ativos. O manager terminou com cinco gerações residentes e os quatro workers reunidos. O SHA-256 comum da saída foi `bf0391c5e7aad2aa22c730d56c07213fadcd0db1b7801d5dd58e1533f9aaba24`. O grafo do FFN preservou os três biases, SwiGLU, máscara, pesos e a ordem das somas. [Cliente nativo](layer.cpp) · [Observador de slots](slot_witness.h)

**Custo e âmbito.** A preparação leu 67 743 872 B em 32 pedidos ao GGUF original no NVMe, autenticou as 30 componentes e criou um pack de 66 293 760 B. Os 12 inputs ocuparam 75 879 200 B. A família medida durou 62,316 s com o inventário, pico de RAM de 200 413 184 B no cgroup, zero swap e zero processos GPU de cálculo observados. As temperaturas máximas amostradas foram 54,25 °C CPU, 43,23 °C GPU e 35,85 °C NVMe. O cgroup contabilizou 132 218 880 B de leitura para a família. O contador agrega os processos e não identifica o tráfego físico de cada braço. O recibo declara as janelas e a frequência da monitorização. [Preparação das fatias](prepare.py) · [Supervisor e limites](profile.py)

Esta prova cobre um tile CPU0, a partir de ativações históricas da chamada warm153, com um índice de teste de cinco entradas. A qualificação da conversa R0 usa 5+148 no prefill. Mantêm-se em aberto a paridade no primeiro decode do modelo inteiro, o custo integrado nominal/código e a autenticação da colocação atual do pack de 61 096 329 216 B. Para a triagem de custo bastam o pack parcial e a mesma agenda. O teste seguinte deve cobrar os READ, a espera e a última publicação com quatro workers, comparando STAGED e DIRECT em ordem emparelhada. Em C293, os ganhos adicionais para a linha de 8% eram 0,102 s no nominal e 0,524 s no código. A meta de seis passos por segundo exigiria retirar 3,333–3,378 s e 4,826–5,354 s dos respetivos decodes de 32 passos. [Custo histórico e limites](../packed_cpu_views/README.md) · [R0 operacional](../nvme_conversation/README.md)

**Reprodução.** O protocolo precedeu a medição no commit `010c37c3`. O build usou `b1bc480fdc0d7ad5b21dac1d781c54aebf93d28c`, a preparação `6be3ec0456beefd433122067002945be7c20bb55` e a execução `e26b1bb3718676a253687ef150c337a1c2062f6a`. O supervisor conferiu que as fontes nativas eram idênticas entre build e medição. Os SHA dos ELF, bibliotecas, fontes e referências estão no recibo. O arquivo do projeto conserva os binários e a telemetria. O GGUF e os cinco registos preparados permanecem privados no portátil. [Arquivo 15](../private_archive/part-15.json)

```sh
study=research/qualification-retake/packed_real_layer
python3 -B -m unittest discover -s "$study"
python3 -B "$study/build.py" --repo "$CLEAN" --backend "$C291" --libs "$C269_LIBS" --new-output-dir "$NEW_BUILD"
python3 -B "$study/prepare.py" --repo "$CLEAN" --lab "$C7" --model "$MODEL_NVME" --placement "$PRIVATE_PLACEMENT" --new-output-dir "$NEW_INPUT"
python3 -I -B "$study/profile.py" --checkout "$CLEAN" --expect-head "$HEAD" --build-dir "$NEW_BUILD" --build-sha256 "$BUILD_SHA" --input-dir "$NEW_INPUT" --input-sha256 "$INPUT_SHA" --libs "$C269_LIBS" --c55-receipt "$FRESH_C55" --c55-sha256 "$C55_SHA" --unit "$UNIQUE_UNIT" --new-output-dir "$NEW_RUN"
python3 -B "$study/compact.py" --raw "$NEW_RUN" --new-output-dir "$NEW_COMPACT"
```
