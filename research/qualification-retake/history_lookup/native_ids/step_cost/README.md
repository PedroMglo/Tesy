# Quanto tempo ocupavam as posições que B3 poderia saltar?

Nas 46 avaliações AR da sessão nominal C281 DEBUG, **as 12 posições dispensadas pela cópia causal somaram 2,420565 s** entre marcos consecutivos do produtor do log. As 23 ordinárias consumiram em média 222,06 ms, as 11 âncoras de proposta 217,40 ms e os 12 saltos 201,71 ms. Cobrar cada verificação ao preço da âncora correspondente deixaria **334,61 ms no total** para coordenação e custos adicionais até 6 tok/s. Distribuir uniformemente o tempo nativo do próprio DEBUG pelas 46 posições daria 501,68 ms. A atribuição por posição no relógio monotónico do sampler permanece **INCONCLUSIVE**. O custo do B3 do target continua **NOT_RUN**. [Pré-registo](protocol.md) · [Recibo integral](evidence/receipt.json)

| Janela após o primeiro ID do prefill | AR ordinário, n / s | Âncoras com proposta, n / s | Saltos, n / s | Span do produtor | Orçamento médio B3 para −15% | Orçamento médio B3 para 6 tok/s |
|---|---:|---:|---:|---:|---:|---:|
| 32 avaliações | 19 / 4,309638 | 7 / 1,428328 | 6 / 1,381681 | 7,119647 s | 248,866 ms | — |
| 46 avaliações até EOG | 23 / 5,107364 | 11 / 2,391364 | 12 / 2,420565 | 9,919293 s | 302,185 ms | 247,815 ms |

A janela de 32 é um recorte diagnóstico. Para −15% no próprio turno completo cabem 3,324035 s nas 11 verificações e em toda a coordenação, cerca de 1,39002 vezes a soma das âncoras. Para 6 tok/s o relógio do servidor conta os 47 IDs incluindo o produzido pelo prefill. O preço resulta de (47/6 s − 5,107364 s)/11, ou 1,13992 vezes a âncora média. São cenários que conservam o custo das posições ordinárias e tomam o intervalo do produtor como aproximação. M3 permanece PARTIAL e M4 NOT_MET. O custo por verificação incluirá três linhas, as combinações adicionais de experts, as páginas de KV, as correções por rejeição e a coordenação. [Fixture de propostas e rejeições](../b3_fixture/README.md)

**Relógio e sensibilidade.** A fonte C269 marca cada entrada do log no produtor com o relógio civil, após obter espaço na fila e formatar a mensagem. O servidor obtém o tempo monotónico ao aceitar o token, antes da emissão da mensagem de diagnóstico. O escritor assíncrono imprime o instante já guardado. O span entre 78 amostras do T1 foi 19,692597 s, 4 µs acima do decode nativo. No T2 o span de 47 amostras ficou 5 µs abaixo dos 9,919298 s nativos. A SSE expôs tempo acumulado apenas na última contagem (78 e 47). Esses totais não identificam os atrasos de cada produtor entre o sampler e o registo, mudanças de relógio ou o instante monotónico de cada amostra.

Repetindo a partição nos marcos em que o token entra no lote seguinte e conservando a última amostra como fim, o limite médio de 6 tok/s passa a 247,814 ms. A ordem das posições importa: quaisquer 12 dos 46 intervalos do produtor poderiam somar entre 1,623895 s e 3,632646 s. Os quatro cenários de relógio que satisfazem o critério de compatibilidade do total, entre os nove pré-registados, dão envelopes condicionais entre 241,894 e 253,736 ms/B3 para 6 tok/s. São extremos conservadores; compatibilidade com o total não demonstra uma calibração. Sem hipótese sobre relógios ou sobre o atraso entre marcos, o único envelope usado para um subconjunto próprio de posições nativas é de zero a 9,919298 s. [Verificador e modelo dos extremos](screen.py)

**Condição para avançar.** O dado mais barato para apertar a atribuição são os instantes `t_now` que o próprio C269 obtém após cada amostra, associados a slot, task e contagem. O tempo das três linhas só é identificável depois de verificar a paridade das posições relevantes e medir verificações completas, parciais e rejeitadas contra AR nos mesmos estados. Os números acima pertencem à sessão DEBUG selada em part-29. A comparação antiga baseada em média usa o seu próprio relógio OFF e continua separada. [Sessão e autoridade dos IDs](../README.md)

**Reprodução.** Pré-registo `9fea5dfc`, programa `4620e7ad4e23242d5ff7eef7644d18d1f7d42bae`. R01 terminou em 0,07 s com 20 496 KiB antes da análise, quando o Git tentou criar threads de lstat dentro do limite de endereços. R02/R03 desativaram a leitura paralela do índice só nesses processos. Ambos demoraram 0,08 s, com 23 496 / 23 544 KiB, e emitiram os mesmos 25 315 B, SHA-256 `349232a005c280245bd1de5e00fc4ee7863869aa2d88a69e87498e8d30fa1bde`. O arquivo privado part-31 preserva os três recibos originais (50 697 B), manifesto SHA-256 `6cda3fb671fb50ba5ca7f4dfa8e547fdd8861f8aa19ba3cd7e8140785031ff76`. Quatro testes sem modelo, incluindo enumeração dos atrasos nos extremos de subconjuntos. Nenhum forward novo, nenhuma GPU e nenhuma leitura de pesos. [Falha R01](evidence/controller-failure.json)

Em checkout limpa, escolher um destino diferente em cada invocação.

```sh
p=research/qualification-retake/history_lookup/native_ids/step_cost
env GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.preloadIndex GIT_CONFIG_VALUE_0=false \
  GIT_CONFIG_KEY_1=index.threads GIT_CONFIG_VALUE_1=1 \
  timeout 120 prlimit --as=536870912 -- python3 -IB "$p/screen.py" \
  --capture "$PART29/tesy-natural-ids-capture-20261125-r01" \
  --verified "$PART29/tesy-natural-ids-verified-20261125-r01" \
  --backend "$C7/backends/c269-layer-last-use" --new-output-dir "$NOVA_SAIDA"
```
