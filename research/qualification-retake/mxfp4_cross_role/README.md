# Quanto poupa a relação entre as três matrizes do expert?

**NO_GO para implementar este codec no regime de banco fixo.** Nos 64 experts reais da C287, usar as coordenadas correspondentes em gate, up e down eleva o teto de poupança de 9,992% para **10,659%**. O melhor expert admite no máximo 14,839%. Mesmo concedendo esse melhor resultado a todas as leituras de ambas as fases, descodificação gratuita e todas as lacunas de prefill escondidas, ainda faltam **0,767–0,985 s** para o primeiro conteúdo final. A escolha da cache pode mudar as chaves que terão de ser lidas. O limite abrange a distribuição e a política aqui especificadas. [Pré-registo](protocol.md) · [Recibo com os quatro cruzamentos](evidence/receipt.json)

| Destino | Experts | Bytes de pesos alinhados | Piso codificado com alinhamento | Teto agregado | Melhor expert |
|---|---:|---:|---:|---:|---:|
| CPU | 32 | 423 100 416 | 377 188 352 | 10,851% | 14,839% |
| CUDA | 32 | 423 100 416 | 378 818 560 | 10,466% | 12,113% |
| Todos | 64 | 846 200 832 | 756 006 912 | 10,659% | 14,839% |

**MEDIDO** nos bytes originais. O contador autenticou os 384 componentes e reproduziu os 192 histogramas espaciais ao remover do contexto as outras matrizes. **FORMAL** para os estados byte-rANS, com cabeçalhos, tabelas e reconstrução gratuitos. Nenhum dos 64 registos passa o gate de 20%. Só descrever as tabelas ocupadas no formato denso exemplificado custaria 104 830 240 B, antes dos índices. Este custo depende da representação implementada. O piso acima concede tabelas gratuitas para beneficiar o candidato. [Prova do piso finito](../mxfp4_entropy/prova.md) · [Resultados por expert](evidence/experts.json)

### Quanto teriam de encolher os registos?

**ESTIMADO para o pedido nominal R02**, conservando o trabalho, os preços de SET observáveis e a parte exterior do decode. A tabela dá a redução mínima de bytes admitida pela grelha de uma parte por milhão, para alcançar os dois alvos simultaneamente. RP significa GGUF seguido de pack, PR a ordem inversa. Cada coluna identifica as ordens físicas independentes do prefill e do decode. A sensibilidade usa o preço observado em cada fase e escala linearmente as leituras com os bytes.

| Tempo do prefill que fica exposto | RP/RP | RP/PR | PR/RP | PR/PR | Défice com o melhor expert em todos os jobs |
|---|---:|---:|---:|---:|---:|
| Serial | 36,3606% | 36,5695% | 34,8700% | 35,0888% | 1,918–2,136 s |
| Pipeline ideal de duas tiles | 28,2807% | 28,5162% | 26,6009% | 26,8476% | 1,126–1,345 s |
| Todas as lacunas gratuitas | 24,6118% | 24,8594% | 22,8461% | 23,1054% | 0,767–0,985 s |

Na população real, a amostra cobre **22/1 058** leituras do prefill e **11/797** do decode. A compressibilidade dos restantes pesos continua desconhecida. Reabrir o investimento se a população efetivamente paga de outra política mostrar margem nos dois tiers ou se outro formato de acesso exato alterar o piso. Nenhum codec, forward do modelo ou cálculo GPU foi executado. [Preços físicos anteriores](../phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/prefill_frontier/transport/joint/README.md)

### Reprodução

Protocolo `e6fd82f8`, execução `25f259791c822d3d453e356f0d183d001f7f230d`, árvore `3ce64ffe099eb965c1ba34ce2798231a445114be`. Dois processos em checkout limpa leram uma vez cada a amostra privada de 848 560 128 B. Duraram 11,48 / 9,99 s, com RSS máxima de 83 876 / 83 928 KiB. Ambos produziram SHA-256 `58703cbf3ea6ee5807f39fae8d1d54b50b73810c5e16779743d32505afd292ca` para o recibo e `fd0cbf668f27a4a719cbf638a817debd2ca0e4039bdaacd4b6d716c5fd078853` para os dados por expert. A parte 72 conserva também as auditorias de capacidade e a fixture do manager. [Manifesto do arquivo privado](evidence/archive.json)

```sh
M=research/qualification-retake/mxfp4_cross_role
env LC_ALL=C OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 245s \
  prlimit --as=402653184 --cpu=240 --fsize=8388608 python3 -IB "$M/screen.py" \
  --results-root "$C7_RESULTS" \
  --sample-pack "$C7_RESULTS/c283-exact-expert-service-epoch-20261006T194311Z/pack/sample64-v1.bin" \
  --prefill-plan "$ARCHIVE/part-69/tesy-prefill-transport-plan-20261125-r01/plan.json" \
  --decode-plan "$ARCHIVE/part-65/tesy-decode-transport-prepare-20261125-r01/plan.json" \
  --decode-rp "$ARCHIVE/part-66/tesy-decode-service-20261125-r01" \
  --decode-pr "$ARCHIVE/part-66/tesy-decode-service-20261125-r02" --new-output-dir "$NEW"
```
