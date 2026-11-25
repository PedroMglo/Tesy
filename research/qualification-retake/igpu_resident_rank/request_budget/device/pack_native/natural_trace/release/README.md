# Primeira procura de cada expert no pack C291

**No próprio braço P, reduzir só o preço das primeiras leituras na wave que as libertou é insuficiente para 10 s ao primeiro final, mantendo o restante fixo e o decode a 6 tok/s.** Mesmo a metade do preço medido do READ, o piso é 12,848 s. Concedendo antecipação perfeita desde a entrada das duas calls e removendo todo o restante trabalho nesse intervalo, o piso de volume passa a 10,107 s a 4,5 GB/s ou 9,012 s a 8 GB/s. A segunda taxa deixa a implementação em aberto. [Recibo compacto](evidence.json)

As duas calls procuraram 1 751 chaves distintas. Havia 899 entre os 1 440 residentes à entrada. Das 852 restantes, 567 precisaram da primeira procura na própria wave e 285 tiveram preload ou outra libertação. Neste pedido, os subconjuntos de libertação estrita e observada coincidiram. A soma de spans disjuntos dos callbacks é 5,898856 s; o envelope completo entre a entrada da primeira call e o retorno da segunda é 9,607863 s.

| Libertação estrita | Waves com custo | Primeiras leituras | Bytes devolvidos | Piso READ a 1× | Piso READ+SET a 1× |
| --- | ---: | ---: | ---: | ---: | ---: |
| Call de 5 | 29 | 51 | 674 316 288 | 0,278374 s | 0,302904 s |
| Call de 148 | 136 | 516 | 6 822 494 208 | 2,790181 s | 3,001627 s |
| Total | 165 | 567 | 7 496 810 496 | 3,068555 s | 3,304532 s |

| Piso do primeiro final | Decode 6 tok/s | 8 tok/s | 10 tok/s |
| --- | ---: | ---: | ---: |
| Mesmas libertações, READ a 1× | 14,382 s | 12,424 s | 11,249 s |
| Idem, READ a 0,8× | 13,768 s | 11,810 s | 10,635 s |
| Idem, READ a 0,5× | 12,848 s | 10,889 s | 9,714 s |
| Idem, READ+SET a 1× | 14,618 s | 12,660 s | 11,485 s |
| Mesmas libertações, volume útil a 4,5 GB/s | 12,979 s | 11,021 s | 9,846 s |
| Idem, 8 GB/s | 12,250 s | 10,292 s | 9,117 s |
| Antecipação desde a entrada, volume útil a 4,5 GB/s | 10,107 s | 8,149 s | 6,974 s |
| Idem, 8 GB/s | 9,012 s | 7,054 s | 5,879 s |

Para a antecipação são necessárias 852 aquisições de origem, 51 procuradas pela primeira vez na call de 5 e 801 na de 148. Representam 11 262 758 400 B úteis ou 11 265 048 576 B devolvidos na agenda de referência. A diferença de 107 ms no cenário a 4,5 GB/s depende da taxa, da ausência de uma fonte em T1 e do decode fixado a 6 tok/s. A tabela completa para volume devolvido e SET está no recibo.

O revisor aceita o PFJ do braço P após confirmação do ficheiro físico por FD, da rota natural e do relógio HTTP. No mesmo processo de análise, chamar `measure(rows, host_trace(rows), receipt["rows"][1])` depois do sucesso de `audit_arm`. As entradas são as duas calls de prefill, com 5 e 148 posições. O serviço de cada geração compreende um pread e três SET pelo mesmo worker. [Auditoria de origem e rota](../analyse.py) · [Auditoria do serviço e do drain](../jobs.py)

O universo conta uma vez cada par camada/expert efetivamente procurado. A chave ganha crédito integral quando já está READY ou LOADING à entrada. Uma recarga ou promoção posterior contribui zero para o piso de libertação estrito. As linhas do resultado separam três premissas.

| Resultado | Trabalho cobrado | Tempo substituível antes do primeiro final |
| --- | --- | --- |
| `first_wave` | Primeira reserva por procura, na primeira wave ou na remap sem waves, com a geração e a publicação provadas | União das callbacks das duas calls |
| `as_observed` | Também as primeiras reservas por procura posteriores, mantendo as respetivas libertações observadas | Mesma união |
| `earliest_allowed_at_entry` | Volume de uma origem por chave ausente, ainda que pudesse começar logo à entrada | Envelope inteiro entre entrada da call 5 e retorno da 148, incluindo o intervalo entre elas |

Os preços de READ e READ+SET foram definidos separadamente para quatro workers. A fração de serviço a 1×, 0,8× ou 0,5× escala os tempos por geração; filas e lacunas entre operações são gratuitas. O volume útil de cada geração é 13 219 200 B e o pedido ao FD é 13 221 888 B. A coluna retornada admite short suficiente no padding. No cenário de antecipação, usa a menor contagem efetivamente retornada por chave no prefixo, sob a hipótese de que a nova origem também exige esse volume. Os cenários a 4,5 e 8 GB/s decimais exigem que os bytes considerados atravessem integralmente um recurso com esse teto. No pin C291, o SET CUDA chama cudaMemcpyAsync e sincroniza a stream da thread antes de retornar. O regresso confirma a entrega do peso. O PFJ não cronometra o instante exato do fim do DMA nem o último kernel que lê o slot. [Fonte do backend e fronteira da cópia](../../../../../../direct_gpu_path/README.md)

A margem é `10 s − piso do primeiro final`. As projeções mantêm o exterior fixo e concedem antes do primeiro final toda a poupança hipotética dos 47 outputs no decode, a 6, 8 ou 10 tok/s. Uma margem negativa exclui aquele cenário. Uma margem positiva deixa por demonstrar a política, o trabalho residual e o serviço real. Uma fonte adicional em T1, antecipação entre camadas e uma taxa física diferente exigem outra conta. Cada projeção usa um único piso.

Cinco testes sintéticos exercitam cinco jobs em quatro workers, hit/LOADING na entrada, preload promovido, nova geração para a mesma chave, wave com elegibilidade anterior, short suficiente, SET ausente ou corrompido e interseção indevida de intervalos. Podem ser repetidos com `python3 -IB test_review.py` neste diretório. Os testes não abrem o journal privado.

O protocolo de medição foi congelado em `61b76781`, SHA-256 original `bb7cbfe1861a668e52eb442855b9eec5f29e6e728809d245f7fb66b6b4b9e944`. A revisão editorial posterior corrige o caminho relativo do antecedente GGUF. [Protocolo](protocol.md)

## Reproduzir o braço ON

Na checkout congelada, indicar o SHA-256 de `family.json` recebido separadamente e um diretório de saída novo. O comando funciona também depois de relocalizar a família completa.

```sh
prlimit --as=536870912 --cpu=120 -- python3 -IB run.py \
  --family-dir "$FAMILIA" --family-sha256 "$SHA_FAMILIA" \
  --new-output-dir "$NOVO"
```

O comando confere a cadeia de digests de `ON/arm.json`, `ON/receipt.json` e `ON/journal-audit.json`, o PFJ ouvido pelo produtor e a fonte do auditor. Reabre os ficheiros privados dos dois turnos, repete a conservação por geração, o confronto da rota e a localização do primeiro final, e exige a igualdade da auditoria inteira com a versão selada na família. O recibo de saída inclui o estado de transferência dos clocks publicado pela família. Com os digests independentes do arquivo, acrescentar `--t2-result-sha256 "$SHA_RESULT"` e `--t2-request-sha256 "$SHA_REQUEST"` para conferir também os bytes integrais desses dois ficheiros. Sem esses parâmetros, a família atesta as métricas e projeções verificadas; o comando regista os dois digests da cópia efetivamente lida.

Três testes adicionais de cadeia de autoridade, reabertura e preservação de falha correm com `python3 -IB test_run.py`. A saída `FAIL_PRESERVED` deste teste é a contraprova deliberada de um PFJ alterado.

A família `e5012e559a2403145abc6f5317bddc8b83f95f1e09b592eb83a6baa2c18980a9` passou a banda descritiva de custos do bloco único. As duas execuções da checkout `df0bae6652570e7e24c2a613d503be327d35450f` e uma terceira que reabriu a part-97 produziram os mesmos 21 893 B, SHA-256 `440c4b1d74846c35efc4e69c28859a07608276a50dcb9a178d8de9eacb8d1cd7`. Correram em 0,44 / 0,41 / 0,40 s, com pico máximo de 56 904 KiB RSS, sem falhas. As três invocações passaram ambos os SHA HTTP externos. O [compacto](evidence.json) conserva as identidades, contagens e pisos inteiros em ns, com uma única cópia das duas seleções iguais.
