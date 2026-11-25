# Quanto resta dos 10 s aos preços individuais medidos no NVMe?

Com 353 entradas, a primeira travessia conduz a um piso de **10,019168047 s**, excedendo o alvo em **19,168047 ms**. A segunda conduz a **9,993403747 s**, com apenas **6,596253 ms** para qualquer aumento líquido no caminho crítico. A primeira fecha a hipótese ao seu preço de leitura. Na segunda, uma seleção com conhecimento de T2 satisfaz os dois pisos e deixa por demonstrar que a escolha é causal e que o restante trabalho cabe. **INCONCLUSIVE** quanto a sustentar o regime com ambos os preços físicos. Nenhuma travessia mediu o tempo de resposta de um cliente. [Protocolo](nvme-protocol.md) · [Recibo](evidence/nvme.json)

| Capacidade | Piso ao preço da travessia 1 | Folga ou défice | Piso ao preço da travessia 2 | Folga ou défice | Piso do payload de prefill, travessia 1 / 2 |
|---|---:|---:|---:|---:|---:|
| 0 | 12,474500 s | −2 474,500 ms | 12,424185 s | −2 424,185 ms | 11 262 758 400 / 11 262 758 400 B |
| 239 | 10,751540 s | −751,540 ms | 10,724101 s | −724,101 ms | 10 099 468 800 / 10 192 003 200 B |
| 353 | **10,019168 s** | **−19,168 ms** | **9,993404 s** | **+6,596 ms** | 8 989 056 000 / 8 989 056 000 B |
| todas as 1 698 | 9,601246 s | +398,754 ms | 9,574866 s | +425,134 ms | 4 335 897 600 / 4 335 897 600 B |

As 353 chaves foram selecionadas de novo para cada preço. Em ambas as travessias, 172 são primeiras procuras úteis do prefill. O limite de 47 saídas admite 10 690 306 614 B; a sensibilidade de 46 passos admite 11 440 306 616 B. Os dois critérios de volume usam a mesma seleção que dá o piso temporal de cada cenário. Reter todas as 1 698 vítimas excede o perfil de RAM estudado. A margem líquida disponível no caminho crítico pode incluir trabalho concorrente cuja soma de worker-tempo seja maior. Cobrar esse trabalho exige identificar as dependências de cada cópia e a espera por dados. [Orçamento de memória e resultado com os preços integrados](README.md)

A comparação autenticou as 441 waves, as 875 gerações e os 2 625 componentes na mesma ordem de serviço nos planos dos dois pedidos. Conferiram-se a posição da wave, a identidade do expert e do slot, a geração, o papel, o intervalo lógico e o pedido alinhado de cada componente. A identidade do plano liga os campos ao código que emitiu os tempos; o journal físico regista o site, o expert, o worker e os três intervalos. Os 2 625 hashes do payload das duas travessias coincidiram em ordem. Cada uma pediu 11 577 561 088 B alinhados para servir 11 566 800 000 B lógicos. [Travessias e recibos do NVMe](../cold_read_fixture/README.md)

**TRACE_DERIVED com preços de READ medidos.** Usou-se apenas a duração de cada syscall da travessia correspondente. A soma das 875 cadeias foi de 13,859563837 worker-s na primeira e de 13,747699654 worker-s na segunda. Os 1 894 serviços com SET, os 5 682 SETs, o instante de libertação de cada wave e o custo exterior de 6,008451991 s pertencem à própria sessão T2. O cenário de 353 entradas assumia 10,128999 s com os preços dos READs integrados. A mudança de preço reduz esse piso em 109,831 ms ou 135,595 ms, respetivamente. O controlo de contenção integrado, o custo de retenção T1 e a qualificação de produto continuam em aberto. M4 permanece **NOT_MET**.

## Reprodução

Pré-registo em `b02d0237`, verificador em `083139bb`. As seis verificações sintéticas abrangem os componentes, a ordem, o deslocamento da época dos relógios e os casos adversos do solver. Ambas as reproduções CPU abriram arquivos imutáveis e destinos distintos. A primeira usou 0,89 s e 75 316 KiB de RSS máximo; a segunda, 0,90 s e 75 396 KiB. O recibo de 8 886 B reproduziu-se byte a byte, SHA-256 `210d3bb2eeb8ae907f83320755d09474ae55059450a2261db95fe447a4128bce`. A identidade do GGUF foi verificada por inode, sem ler os pesos.

```sh
STUDY=research/qualification-retake/phase_fd/integrated/t1_set_floor
python3 -IB -m unittest discover -s "$STUDY" -p 'test*.py'
timeout 120s prlimit --as=536870912 --cpu=120 --fsize=1048576 -- \
  python3 -IB "$STUDY/nvme.py" --part "$PART40" --nvme-part "$PART38" \
    --model "$MODEL" --inventory "$INVENTORY" --prepared-dir "$PREPARED" \
    --score-dir "$LOCAL_SCORE" --copy 1 --new-output-dir "$NEW"
cmp "$NEW/receipt.json" "$STUDY/evidence/nvme.json"
```

A segunda reprodução usou `--copy 2` e os recibos correspondentes à segunda preparação e à segunda avaliação local.

A [verificação das sete lacunas do próprio worker](gaps.md) fecha ambos os cenários com esse custo a 100%. O segundo preço ainda admite 83,06% dessas durações no piso.
