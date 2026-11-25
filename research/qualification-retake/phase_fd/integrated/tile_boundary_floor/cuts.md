# Quanta liberdade de residência é necessária nos 40 slots?

**HEADROOM_ONLY para o banco das 353 últimas vítimas.** No nominal, o oráculo tem de poder mudar os residentes depois de cada uma das quatro primeiras tiles da chamada de 148. Se conservar o conjunto R0 em apenas um desses quatro cortes, a melhor escolha ainda custa 870 leituras. O orçamento admite 808 na convenção de 47 tokens e 865 na sensibilidade de 46. Os cálculos mantêm a ordem 5+148, a divisão 32+32+32+32+20, os grupos simultaneamente protegidos e os residentes do controlo nos dois retornos externos.

| Banco anterior a T2 | Quatro cortes fixos | Melhor com três cortes livres | Quatro livres | Decode de 46 avaliações, a partir de R0 |
|---|---:|---:|---:|---:|
| Vazio | 1 133 | 1 012 | 944 | 784 |
| Últimas 353 publicações | 1 066 | 946 | 870 | 647 |
| Últimas 353 vítimas | 985 | 870 | 793 | 641 |

Com as 353 vítimas, permitir a mudança só em camadas CPU custa 869 leituras, ou 909 se permitida só em camadas CUDA. No ramo de 47 tokens, pelo menos 24 das 36 camadas precisam de liberdade de residência, mesmo podendo escolhê-las depois de ver T2. Na sensibilidade de 46 precisam de pelo menos 13. Em ambos os ramos só um dos 16 subconjuntos passa o crivo de volume. O oráculo tem custo zero para servir do banco em RAM, permutar slots, construir o banco e recuperar pesos da RAM em cada corte. Libertar ainda o estado após a chamada de 5 baixa o ótimo de 793 para 776.

As 793 cargas requerem 10 482 825 600 B, das quais 505 cargas pertencem às camadas CPU e 288 às CUDA. Para uma taxa útil de 4,5 GB/s e um decode a exatamente 6 tok/s, a margem nominal é de **46,107 ms** (207 481 014 B). A sensibilidade de 46 deixa 212,774 ms. A banda útil mínima só para o payload nominal seria 4,413 GB/s. As taxas são hipóteses da triagem. Esta agenda conhece o futuro, o cálculo ignora o custo de copiar e de coordenar, e há trabalho do grafo e do cliente por cobrar. O orçamento do decode de 872 admissões tem o seu próprio denominador. [Todos os subconjuntos, dispositivos e ramos](cuts-receipt.json) · [Orçamentos do próprio pedido](../t1_source_bank/README.md)

O algoritmo offline paga as admissões ausentes e protege toda a wave antes de permitir expulsões. O verificador acrescenta ao fim de cada segmento uma wave com o conjunto obrigatório de saída. Os estados observados tinham 40 residentes por camada e estavam drenados. Para cada inclusão entre subconjuntos, o custo só pôde descer em cada camada. O verificador confrontou os extremos com o oráculo independente e com o limite de chaves compulsórias. [Protocolo](cuts-protocol.md) · [Verificador](cuts.py) · [Prova e teste exaustivo do oráculo](../t1_primary_victim/oracle-protocol.md)

Freeze ed693945. Duas reproduções em 0,67 e 0,72 s deram o SHA-256 de7e2eb8b29332ea70cb5013c55e2cd8b23077c537c36a52f119089716ce9801, com pico RSS até 78 036 KiB, zero forwards e zero leitura de pesos. O arquivo privado part-57 preserva os dois recibos, com manifesto SHA-256 3530189c17502ed6557a3cb36b6c0b192e9c4cccfc28998374afcb48ee157e12.

```sh
unit=research/qualification-retake/phase_fd/integrated/tile_boundary_floor
timeout 120s prlimit --as=536870912 -- python3 -IB "$unit/cuts.py" \
  --part "$ARCHIVE/part-40" \
  --selection "$ARCHIVE/part-56/tesy-source-bank-seal-20261125-r01/selection.json" \
  --new-output-dir "$NOVA_SAIDA"
cmp "$unit/cuts-receipt.json" "$NOVA_SAIDA/receipt.json"
```
