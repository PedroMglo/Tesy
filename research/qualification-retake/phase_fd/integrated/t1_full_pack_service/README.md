# Entrega dos quatro grupos a partir do ficheiro integral

O plano selado fixa 29 registos e 87 componentes. O verificador da preparação conferiu os 29 offsets reais, digest `6e09c22efa24a4945bf9fcea0701b3dbcc4102a44bb58b83ab1b1c45f7df8f88`. A seleção vem da mesma conversa, do mesmo banco e das mesmas duas políticas da fixture anterior. A primeira célula só abre depois de a colocação integral estar autenticada e as janelas selecionadas, incluindo o padding, reproduzirem o digest da fatia. [Protocolo](protocol.md)

A medição exige uma checkout limpa, um recibo PASS da colocação, o SHA-256 desse recibo fixado para a família, o GGUF original já colocado, uma C55 dentro da validade, C118 por braço e a identidade do monitor/driver que passou na fixture dos destinos nativos. Usar o mesmo ambiente dessa fixture, quatro workers e um scope novo por processo. Usar uma nova raiz privada por comando. Os argumentos `ARM1` e `ARM2` identificam as unidades sem sufixo.

```sh
cmd=(python3 -IB "$UNIT_DIR/measure.py" --commit "$FROZEN_COMMIT"
  --placement "$PLACEMENT/receipt.json" --placement-sha256 "$PLACEMENT_SHA"
  --model "$MODEL" --plan "$PLAN" --map "$STATIC_MAP" --ram-dir "$HISTORICAL_RAM")
systemd-run --user --scope --unit="$ARM1" -p MemoryHigh=2G -p MemoryMax=2G -p MemorySwapMax=0 \
  -p RuntimeMaxSec=230 env LD_LIBRARY_PATH="$MONITOR" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  "${cmd[@]}" --arm 1 --unit "$ARM1" --c55 "$C55" --c55-sha256 "$C55_SHA" --new-output-dir "$FIRST"

systemd-run --user --scope --unit="$ARM2" -p MemoryHigh=2G -p MemoryMax=2G -p MemorySwapMax=0 \
  -p RuntimeMaxSec=230 env LD_LIBRARY_PATH="$MONITOR" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  "${cmd[@]}" --arm 2 --unit "$ARM2" --c55 "$C55" --c55-sha256 "$C55_SHA" \
  --first-dir "$FIRST" --first-sha256 "$FIRST_SHA" --new-output-dir "$SECOND"
```

O revisor aceita dados arquivados, confirma os tempos diretamente nos journals e preserva os quatro sinais por contraste, tier e fase. Não abre o pack ou o modelo. A comparação com a fatia reporta os dois processos históricos em separado. Uma nova C55 para o segundo processo pode ser fornecida em `--second-c55`.

```sh
python3 -IB "$UNIT_DIR/review.py" --first "$FIRST" --first-sha256 "$FIRST_SHA" \
  --second "$SECOND" --second-sha256 "$SECOND_SHA" --c55 "$C55" --placement "$PLACEMENT/receipt.json" \
  --placement-sha256 "$PLACEMENT_SHA" --plan "$PLAN" --ram-receipt "$HISTORICAL_RAM/receipt.json" \
  --map "$STATIC_MAP" --new-output-dir "$NEW_AUDIT"
```

Os testes sintéticos distinguem offsets integrais e compactos com as mesmas matrizes, rejeitam um endereço de outro expert e recusam um manifesto de tamanho, origem, digest ou estado incorretos. O revisor anterior continua a reproduzir o recibo histórico `c70cb5b267cc26877f8d353c8cdb27c6f7334b392be6c9983ddbbad61e6f57fe` a partir dos seus dois processos. [Resultados anteriores](../t1_native_sink/README.md) · [Censo das 42 waves](../t1_full_workload/README.md)

## Viabilidade de alargar a amostra

O programa atual conserva em memória um exemplar dos pesos de cada expert selecionado para preparar e verificar os destinos. Nos 42 estratos, os 310 registos exigiriam **4 097 952 000 B apenas para estes exemplares**, ultrapassando o cap de 2 GiB antes dos pools e do scratch. O plano de 42 estratos ainda pediria **21 426 974 720 B ao FD por processo** nas cinco passagens de serviço. Uma extensão teria de limitar os exemplares vivos por wave ou subgrupo estável, repetir a preparação fora do relógio e contar essas leituras e a ordem dos acessos no novo orçamento. [Censo selado](../t1_full_workload/evidence/receipt.json)

A soma das quatro células do mesmo censo, incluindo todas as waves dos domínios de prefill e decode, alcança 110 521 798 656 B por passagem de serviço (54 520 057 856 B nas calls 5+148). Cinco passagens custariam 552 608 993 280 B por processo antes de verificação, preparação e reconstituição do estado do primário. São bytes previstos pelas agendas congeladas. O pack integral permite estudar os offsets originais; não remove estes custos. A medição dos quatro grupos pode decidir se vale orçamentar primeiro os 42 estratos.
