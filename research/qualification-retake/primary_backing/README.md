# Reter os experts no destino primário durante o decode

**NO_GO_CONDITIONAL_FIXED_REMAINDER.** Nos quatro braços C294, mesmo permitindo reter gratuitamente todos os experts após a primeira procura, a duração dos READs obrigatórios e o trabalho fora da espera C295 ultrapassam 5,333333 s para 32 passos fornecidos. O resultado mantém-se a 80% das durações de leitura originais. O piso de READ isolado também ultrapassa esse orçamento nos quatro braços à escala original. Com a redução de 20%, apenas o nominal cabe quando se atribui custo zero a todo o restante trabalho. O orçamento representa o alvo de decode nominal e uma comparação comum em código. O avaliador de produto conserva os seus critérios próprios. M3 PARTIAL e M4 NOT_MET. [Pré-registo](protocol.md) · [Recibo](evidence/receipt.json)

| Caso C294 trace-ON | READ puro 1× (s) | READ puro 0,8× (s) | Restante fixo (s) | Com restante, 1× (s) | Com restante, 0,8× (s) | Excesso a 0,8× com restante (s) |
|---|---:|---:|---:|---:|---:|---:|
| Nominal 2 | 5,563 | 4,450 | 1,773 | 7,336 | 6,223 | 0,890 |
| Nominal 3 | 5,559 | 4,447 | 1,831 | 7,390 | 6,278 | 0,944 |
| Código 2 | 6,843 | 5,474 | 1,817 | 8,660 | 7,292 | 1,958 |
| Código 3 | 6,843 | 5,474 | 1,829 | 8,672 | 7,303 | 1,970 |

Em I há 1 411 residentes nos 1 440 slots e zero leituras pendentes. A referência anterior identifica as 779 chaves ausentes e exigidas pelo decode nominal, 505 CPU e 274 CUDA. Em código são 928, com 632 CPU e 296 CUDA. O novo replay associa cada chave à geração da primeira procura entre as 1 152 barreiras. Há serviço obrigatório em 537 grupos nominais e 640 de código. Preservar um expert no destino elimina o job integral nas utilizações seguintes. A relaxação concede quatro workers, remapeamento imediato, capacidade ilimitada após I e reposição terminal gratuita. [Contagem inicial](../cache.md) · [Controlo LRU por tier](../decode_tier_pool/README.md) · [Contraste L2 com cópia](../l2_critical/README.md)

O piso soma as três leituras seriadas por geração e toma o máximo dos ranks em cada grupo. Desconta até 1 µs por leitura pela resolução do journal. Os intervalos estão contidos entre a libertação das rotas e o remap. No próprio relógio de cada braço, **0 µs** da união dos READs obrigatórios caiu fora das esperas nativas P11–P12. As esperas e o restante do C295 recompõem a duração observada; nenhum READ cobrado entra duas vezes. Ao trocar a política, parte do trabalho de fila, despacho ou remap fora da espera pode mudar. A coluna com o restante fixo depende expressamente da sua conservação. As durações de serviço e a sua sensibilidade são TRACE_DERIVED e dependem do serviço observado, incluindo contenção. [Controlos de componentes](../component_ready_bound/README.md) · [Decomposição C295](../../../tools/expert_prediction_scenario.py)

Com esse restante fixo, a escala que ainda permitiria atingir o orçamento, concedendo zero aos outros custos, é no máximo 0,640/0,630 no nominal e 0,514/0,512 em código. À escala 0,8, uma antecipação que apenas sobreponha READ ao trabalho restante teria de recuperar 0,890/0,944 s de parede no nominal, 50,2%/51,6% desse restante. Em código a recuperação necessária é 1,958/1,970 s. Mesmo escondendo todo o restante de 1,817/1,829 s, faltariam 0,141/0,141 s dos próprios READs. Antecipar entre grupos de decode teria de demonstrar essa sobreposição no mesmo caminho crítico. Preparar outras identidades em I pode retirar serviço desde a primeira procura, mas desloca leitura, cópia e ocupação para o incremento ou histórico. Para atribuir segundos a essas chaves seria preciso recalcular o máximo de cada grupo e cobrar a sua preparação no pedido; o défice temporal por si só não determina um número de experts.

Uma nova hipótese deve demonstrar que reduz estas durações, o restante, ou o número de primeiras admissões mediante alteração paga do estado I ou sobreposição anterior à procura. Os números históricos não medem o NVMe contemporâneo, a conversa natural, nem o custo de implementar vistas ou de repor F.

## Reprodução

Protocolo em `f06de996`; código em `41a53e3263ccde6aa66e1e290b1ecf91a52fc888`, árvore `6cfb27aff084d503f916179f2a3e4b71be672e12`. Os quatro testes sintéticos cobrem uma primeira falta obrigatória sem geração, dependências das componentes, serviço sobreposto à parte fixa e decisão no limite. As duas execuções limpas usaram 1,03/1,01 s de parede e 105 916/105 340 KiB de RSS máxima. Cada recibo tem 9 531 B e SHA-256 `44ba456b19a1d4fcd44ecb7127a99db410344e304a4e51474d41dec1847fc9f5`. Zero pesos, uso de GPU ou novas medições físicas.

```sh
python3 -B -m unittest discover -s research/qualification-retake/primary_backing
LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  timeout 120 python3 -B research/qualification-retake/primary_backing/screen.py \
  --raw-dir "$TESY_C294_RAW" --new-output-dir "$DESTINO_NOVO"
```
