# Quanto teria de ganhar uma mudança só no decode?

**Nos dois turnos reais com o pack, seriam necessárias reduções de 98,06% e 97,59% do tempo dos 44 passos até ao primeiro final** se o restante custo exposto se conservasse. As propostas de executar um rank noutra unidade podem ainda contribuir para o débito. Este crivo indica quando será preciso combinar o seu efeito com trabalho no prefill ou nas leituras. O alvo continua a exigir primeiro conteúdo final em 10 s e pelo menos 6 tok/s na mesma receita. [Pedidos originais](../../packed_nvme_manifest/server_profile/conversation/ordens.md) · [Identificação da amostra 45](../../history_lookup/packed_step_budget/README.md)

| T2, braço P | R/O/P | P/O/R |
|---|---:|---:|
| Primeiro conteúdo final, cliente | 18,514554 s | 18,312926 s |
| Passos do produtor entre as amostras 1 e 45 | 8,683044 s | 8,518591 s |
| Tempo disponível para os mesmos 44 passos, mantendo o restante fixo | 168,490 ms | 205,665 ms |
| Orçamento médio por passo | 3,829 ms | 4,674 ms |
| Redução pedida pelo alvo de 6 tok/s, no decode completo de 47 saídas | 1,097 s | 0,934 s |
| Janela do cliente, primeiro raciocínio → primeiro final | 8,088467 s | 7,928046 s |
| Mínimo de bytes de leitura contabilizados ao processo dentro da janela | 10 974 199 808 B | 11 212 161 024 B |
| Máximo de bytes disponíveis no prazo, ligação ideal de 8 GB/s | 1 347 923 680 B | 1 645 323 464 B |
| Fração crítica do mínimo observado | 12,28% | 14,67% |

**MEDIDO / REPRODUZIDO.** O Linux contabiliza as leituras do processo ao submeter I/O à camada de blocos. Os dois mínimos usam exclusivamente amostras inteiras da mesma instância do servidor entre os deltas SSE de raciocínio e conteúdo. O relógio monotónico do cliente fornece as fronteiras. O revisor considera toda a incerteza da origem comum do monitor, até 173,015 ms e 129,940 ms, e o tempo de cada recolha. Pelo menos onze amostras cabem em cada janela. A ligação máxima anunciada pelo NVMe interno é PCIe 16 GT/s ×4. Conceder 8 GB/s cobra zero overhead de codificação e de protocolo. [Contador do kernel](https://docs.kernel.org/filesystems/proc.html) · [Verificador das duas janelas](screen.py)

**CONDICIONAL.** Subtrair a duração S dos passos do produtor à duração F do cliente dá o cenário em que F−S se conserva. A segunda marca do produtor muda o orçamento em 4 µs e 1 µs. Se mais de 12,28% ou 14,67% dos respetivos mínimos ainda tiverem de atravessar a mesma ligação dentro do novo prazo, só a transferência ultrapassa o orçamento mesmo com cálculo gratuito. Uma alteração pode mudar o momento das leituras e a porção que coincide com o cálculo. A fração do tráfego do processo atribuível ao NVMe e as transações que continuam necessárias dentro do novo prazo carecem de provas próprias. O crivo mantém INCONCLUSIVE a atribuição causal a um operador individual. [Recibo por braço e relógio](receipt.json) · [Critérios congelados](protocol.md)

Análise sem carga de modelo, nos dois arquivos privados. Fonte congelada em b13b1739. Uma segunda implementação reabriu as partes 78 e 80 e reproduziu o número de passos, ambos os mínimos e os quatro orçamentos. [Arquivo da unidade](../../private_archive/part-86.json)

```sh
D=research/qualification-retake/igpu_resident_rank/request_budget
python3 -IB "$D/test_screen.py"
python3 -IB "$D/screen.py" --archive "$TESY_PRIVATE_ARCHIVE" --new-output-dir "$NEW_RESULT"
```
