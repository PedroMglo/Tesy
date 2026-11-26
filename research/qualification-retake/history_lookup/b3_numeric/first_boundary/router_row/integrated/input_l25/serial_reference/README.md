# As três posições coincidem até às entradas da atenção da camada 25

**MEDIDO e REPRODUZIDO.** Com o GPT-OSS-120B original na RTX, a execução serial preservou bit a bit o residual da camada 24, a normalização de entrada da camada 25 e as três matrizes de ativação Q, K e V observadas no bloco de três posições. O primeiro corte disponível a divergir nas três posições é a saída de atenção já projetada, `attn_out-25`. Aí diferem todas as 2 880 palavras F32 por posição. O router recebe uma ativação que já mudou. A associação entre esta diferença e o seu mecanismo de cálculo permanece **INCONCLUSIVE**. [Prova por posição e hashes](result.json) · [Pré-registo](protocol.md)

| Tensor | F32 por posição | Diferentes em 189 | Em 190 | Em 191 |
|---|---:|---:|---:|---:|
| Saída FFN e residual de L24, cada | 2 880 | 0 | 0 | 0 |
| Norma antes da atenção L25 | 2 880 | 0 | 0 | 0 |
| Q após RoPE | 4 096 | 0 | 0 | 0 |
| K após RoPE / V antes da cache, cada | 512 | 0 | 0 | 0 |
| Atenção após projeção e bias | 2 880 | 2 880 | 2 880 | 2 880 |
| Entrada do FFN após soma residual | 2 880 | 2 879 | 2 880 | 2 879 |
| Operando normalizado do router | 2 880 | 2 880 | 2 880 | 2 879 |
| Saída do FFN L25 | 2 880 | 2 880 | 2 880 | 2 880 |

Os 33 pares incluem 25 linhas para as quais faltava a referência independente. O novo processo AR usou a biblioteca C269 original e o observador da parte 110. Reproduziu o prefill de 2 248 ficheiros, os cinco vetores completos de 201 088 logits, todos os estados de KV e pool conservados no AR anterior, 885 payloads de ativação comuns a esse AR e as 184 linhas independentes disponíveis em L14–35 na C270. O revisor conferiu os 1 182 payloads de cada geometria e os cinco logits do B3 anterior. A observação serial usou o driver 620.73.04 e o B3 arquivado usou 620.70.06. A igualdade dos controlos históricos cobre as suas fronteiras. Para atribuir as novas diferenças a uma operação é preciso emparelhar também o driver. [Ponte de R0 no driver atual](../../../../../../../packed_nvme_manifest/server_profile/system_driver/README.md) · [Controlo B3](../README.md)

Em `src/llama-graph.cpp` do pin C269, o grafo constrói a atenção sobre o KV e a máscara, expõe `kqv_out` e só depois aplica o peso de projeção e o bias. Em `src/models/openai-moe.cpp`, `attn_out` observa o resultado dessa cadeia. O próximo par tem de observar `kqv_out-25` antes da projeção nas duas geometrias. A igualdade das linhas de Q/K/V atuais não prova o conteúdo, os índices ou a máscara de todos os slots que o kernel realmente consumiu. A mudança de rota, os custos da atenção e o ganho de produto requerem testes próprios.

O C55 e 61 amostras C118 precederam um único arranque de modelo, com tokens fornecidos e zero pedidos de geração. O processo demorou 28,356 s, o scope com C118 89,197 s. Houve 110 observações dos mapeamentos, 6 878 MiB de VRAM, 15 970 095 104 B de pico no cgroup e zero swap. Máximos de 71,125 °C na CPU, 51,38 °C na RTX e 45,85 °C no NVMe. A potência da RTX observada em 42 amostras estima 329,0 J em 27,658 s. A energia total do portátil é desconhecida. O código físico estava em `e3f968b7`, protocolo `ce381921`. A reabertura dos originais e do arquivo produziu o mesmo recibo `6a7915f6de732c9c30df5f61255a21d5aba432f6dc0778f89025bdc633fdcfd1`. [Manifesto 164](../../../../../../../private_archive/part-164.json) · [Revisor](review.py)

```sh
python3 -IB review.py --family "$SERIAL" --reference "$C270_ATUAL" --archive "$ARCHIVE" \
  --receipt-sha256 6cd62fa18eb95c90cd0201b97b05c38b1279570e8b7d465579f0167aa1048935 --new-output-dir "$NEW"
```
