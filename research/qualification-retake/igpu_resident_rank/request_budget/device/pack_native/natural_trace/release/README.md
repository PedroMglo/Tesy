# Primeira procura de cada expert no pack C291

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
