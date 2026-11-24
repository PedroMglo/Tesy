# Capacidade máxima de uma cache escolhida entre experts já reservados

**NO_GO para o caso de código se a seleção ficar limitada às identidades de `seen` no fim do prefixo.** Com 40 slots por camada, materialização inicial gratuita, escolha com conhecimento do futuro e reposição Belady, código ainda requer 718 cargas nos 32 tokens de decode. O máximo admissível é 504. O nominal admite 487 sob as mesmas concessões. Ao acrescentar os experts efetivamente publicados durante os 153 tokens incrementais, os mínimos descem para 418 no nominal e 462 em código. A realização dessa segunda hipótese permanece **INCONCLUSIVE** nos dois casos. [Congelamento](prefix_seen_protocol.md) · [Recibo por braço](prefix_seen_evidence/receipt.json)

| Braço trace-ON | Elegíveis após prefixo / com publicações | Mínimo após prefixo | Folga para 504 | Mínimo com publicações | Folga para 504 |
|---|---:|---:|---:|---:|---:|
| nominal 2 | 2 659 / 2 864 | 487 | +17 | 418 | +86 |
| nominal 3 | 2 659 / 2 864 | 487 | +17 | 418 | +86 |
| código 2 | 2 476 / 3 123 | 718 | −214 | 462 | +42 |
| código 3 | 2 476 / 3 123 | 718 | −214 | 462 | +42 |

Cada identidade designa um par camada/expert. O bitmap no snapshot autoritativo conserva também reservas entretanto expulsas e concede elegibilidade a eventuais reservas canceladas. O prefill incremental acrescentou 205 identidades no nominal e 647 em código. Por camada, o oráculo escolhe entre as elegíveis as primeiras a serem pedidas no futuro, respeita os quatro pins simultâneos e usa Belady para o resto do decode. A preparação inicial e a reposição ótima não são uma política causal demonstrada. [Semântica do bitmap](causal_prefix.md) · [Conservação de gerações e publicações](cache_boundary.md) · [Verificação do solver por enumeração](test_cache_bound.py)

Para 32 tokens, o serviço dedicado de 10 Gbit/s concede 5,333 s no relógio do decode a 6 tok/s. Usando apenas `seen`, o nominal tem 0,183 s de folga e código excede o orçamento em 2,260 s. Com as publicações, a folga é 0,913 s no nominal e 0,448 s em código. Estes saldos têm de acomodar no decode toda a leitura adicional e todo o trabalho restante no seu caminho crítico. Uma materialização anterior também tem custo no relógio do prefill e do primeiro conteúdo final. A projeção atribui custo zero à preparação. O custo real continua por medir. [Cálculo](prefix_seen.py)

A observação em falta é um estado de 36 × 40 slots realmente atingível no primeiro decode por uma escolha que use só informação já disponível, com prova de quando cada expert fica pronto e do custo pago para o reter ou recarregar. Esse estado fixa a entrada para reaplicar a contagem de faltas aos dois casos, mantendo os relógios das fases separados. As frequências reais do prefixo só poderiam melhorar a escolha dentro do inventário A, que já falha em código. Para B, o limite admite um próximo teste de viabilidade causal e não constitui evidência de desempenho do serviço.

Reprodução sem modelo, em 0,957 s e com máximo observado de 103 020 KiB de RSS. Quatro braços e doze ficheiros autoritativos validados por tamanho e SHA-256. Zero pesos, GPU ou novos forwards. Mantiveram-se os limiares e os protocolos M3/M4. [Manifesto C294](../../results/c294-feature-ready-service-window-20261006/raw-manifest.json)

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B \
  research/qualification-retake/prefix_seen.py --raw-dir "$TESY_C294_RAW" \
  --new-output-dir "$TESY_NEW_SEEN_OUT"
```
