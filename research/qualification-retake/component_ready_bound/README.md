# Uma componente pronta pode antecipar o cálculo dentro da camada?

**NO_GO_COMPONENT_READY_FIXED_READ** para seis passos fornecidos por segundo nos quatro decodes C294 estudados. Mesmo concedendo entrega imediata de cada componente e anulando integralmente cópias, cálculo e coordenação, os READs em série de cada geração ultrapassam o orçamento de 5,333333 s. O veredito mantém-se ao reduzir todas as durações de READ em 20%. Trata-se de um limite **TRACE_DERIVED condicional** para uma conversa, com procura autoritativa, mesmos misses e quatro workers. [Pré-registo](protocol.md) · [Recibo por braço](evidence/receipt.json)

| Braço trace-ON | Decode nativo (s) | Piso CPU + CUDA, 1× (s) | Excesso 1× (s) | Piso 0,8× (s) | Excesso 0,8× (s) |
|---|---:|---:|---:|---:|---:|
| Nominal 2 | 9,3815 | 5,0434 + 2,0268 = 7,0702 | 1,7368 | 5,6561 | 0,3228 |
| Nominal 3 | 9,4150 | 5,0136 + 2,0242 = 7,0378 | 1,7044 | 5,6302 | 0,2969 |
| Código 2 | 10,9861 | 6,1184 + 2,3924 = 8,5108 | 3,1774 | 6,8086 | 1,4753 |
| Código 3 | 11,0098 | 6,1163 + 2,3915 = 8,5078 | 3,1745 | 6,8062 | 1,4729 |

Cada braço reconcilia 32 passos, 800 grupos CPU, 352 CUDA e 4 608 seleções ordenadas. No nominal, 762 misses CPU e 319 CUDA originaram 3 243 pares READ e 14 289 955 200 bytes lógicos. Em código foram 927 + 381 misses, 3 924 pares e 17 290 713 600 bytes lógicos. As repetições concordam em contagens e rotas. O replay verifica estado inicial, gerações, as três leituras e cópias, publicação e slots terminais. Subtrai até 1 µs por READ pela resolução do journal, soma as três componentes da geração e toma o máximo dos quatro ranks. Só soma máximos entre grupos causalmente ordenados. O relógio nativo da tabela serve de contexto. A conta usa apenas diferenças internas ao journal de cada braço. [Replay de estado](../cache_boundary.py) · [Referência ordenada](../warm_route_reference/verify.py)

No backend C294 `237e3b8789650fd68b97641c5b8e259d198ed3b1`, `src/llama-moe-stream.cpp` linhas 350–380 percorre as componentes de uma geração no mesmo worker. Cada chamada síncrona ao leitor retorna antes da próxima. A sequência observada distingue o caminho do GGUF pelo par READ e SET de cada componente. Em `src/llama-graph.cpp` linhas 2139 e 2199–2235, a projeção down alimenta as vistas por rank e a soma ordenada. Em `src/models/openai-moe.cpp` linhas 134–153, a saída é somada ao residual e alimenta a camada seguinte. Até quatro workers podem sobrepor leituras de experts distintos. O digest SHA-256 das três fontes, por esta ordem, começa por `270ede951c3911c8`, `d1a2ce42e6493054` e `239407aaa98f8b65`. [Protocolo e pin C294](../../../results/c294-feature-ready-service-window-20261006/protocol.json) · [Instrumentação das componentes](../../../patches/c294-feature-service-window.patch)

**Condição de reabertura.** Mantendo estas dependências e uma escala uniforme, só valores até 0,754342/0,757818 no nominal e 0,626657/0,626876 em código podem sequer caber no orçamento dos respetivos braços, com o restante custo ainda a zero. Para outro serviço ou outra colocação, a observação mínima é um conjunto comparável de intervalos de READ por componente, com rota, geração e fronteira. Uma mudança que permita operações concorrentes no mesmo expert requer o seu DAG e tempos de conclusão conjuntos. As durações históricas incluem o serviço visto pelo worker. A prova deixa em aberto o desempenho de tal arquitetura, o tempo cliente e o resultado M3/M4. A ablação de SSD-LLaMA varia que tensores são obtidos do expert-pack ou do GGUF mapeado. Aqui isolámos publicação antecipada a layout e carga fixos. [SSD-LLaMA §5.3, figura 12](https://arxiv.org/html/2609.18110v1#S5.SS3)

**Reprodução.** Na raiz limpa de `d976a12ca05bc725bde779930730c654a5817b64`, árvore `490d2219209935f8fc23eb8a7d9d98090ffad945`, depois do protocolo `c63f40df`, foram usados dois destinos privados exclusivos. Os recibos integrais são byte a byte iguais, SHA-256 `3473a9506fbb4d4e2e5051b243e9cbce04c76ecb96707a5c0fd3e1628d11eebe`. Custos externos de R01/R02 foram 0,53/0,48 s de parede e 47 412/47 580 KiB de RSS máximo. Quatro fixtures sem modelo verificam sobreposição, identidade, ordem e limiar estrito. Zero forwards e zero uso de GPU.

```sh
python3 -B -m unittest discover -s research/qualification-retake/component_ready_bound
python3 -B research/qualification-retake/component_ready_bound/screen.py \
  --raw-dir "$C7/results/c294-feature-ready-service-window-20261006/raw" \
  --new-output-dir "$NEW_OUT"
```
