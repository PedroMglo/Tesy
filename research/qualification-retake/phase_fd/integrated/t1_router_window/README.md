# Quantos bytes de prefill têm um consumidor comprovado?

**NO_GO para antecipar READ dentro da tile mantendo as mesmas gerações e os acertos das políticas avaliadas.** Todas as 1 263 gerações de R0 tiveram um consumidor na própria tile até ao retorno da segunda chamada. Das 436 iniciadas como preload da wave seguinte, 276 tinham destino CPU e 160 CUDA. O crivo concedia gratuitamente as gerações sem consumidor. Neste pedido a dedução é zero. [Protocolo](protocol.md) · [Fonte e dependências](source.md) · [Resultado integral por fase, tier e braço](evidence/receipt.json)

No nominal, o cenário de 4,5 GB/s e decode a exatamente 6 tok/s dá 10 690 306 614 B disponíveis pela convenção contratual de 47 saídas ou 11 440 306 616 B na sensibilidade de 46 avaliações. No melhor braço ficam 994 cargas, 13 139 884 800 B de payload. Para o primeiro orçamento seria preciso evitar pelo menos mais 186 cargas completas de 13 219 200 B ou entregar **5,531 GB/s úteis**. Para o segundo são 129 cargas ou **5,169 GB/s**. Ambos concedem gratuitamente cálculo, SET, coordenação, preparação de T1 e cleanup dentro do orçamento de prefill. Estes são limiares condicionais ao restante do pedido e ao denominador. O pico físico do SSD e a latência de uma implementação têm outra medição.

| Origem no segundo turno | Estado ao POST | Entradas | Gerações a ler | Payload útil (GB) | Banda mínima a 47/6 (GB/s) | Banda mínima a 46/6 (GB/s) |
|---|---|---:|---:|---:|---:|---:|
| R0 | Sem L2 | 0 | 1263 | 16,696 | 7,028 | 6,567 |
| Vítimas | Vazio | 239 | 1068 | 14,118 | 5,943 | 5,553 |
| Vítimas | Recência | 239 | 1052 | 13,907 | 5,854 | 5,470 |
| Vítimas | Vazio | 353 | 1026 | 13,563 | 5,709 | 5,335 |
| Vítimas | Recência | 353 | 994 | 13,140 | 5,531 | 5,169 |
| Publicações | Vazio | 239 | 1231 | 16,273 | 6,850 | 6,401 |
| Publicações | Recência | 239 | 1215 | 16,061 | 6,761 | 6,318 |
| Publicações | Vazio | 353 | 1181 | 15,612 | 6,572 | 6,141 |
| Publicações | Recência | 353 | 1149 | 15,189 | 6,394 | 5,974 |
| Publicações | Votos | 353 | 1156 | 15,281 | 6,433 | 6,011 |
| Vítimas | Votos | 353 | 1001 | 13,232 | 5,570 | 5,205 |

Na chamada de 5 houve 40 admissões CPU e 11 CUDA. Na chamada de 148 houve 492/284 por procura e 276/160 por preload, CPU/CUDA. A associação segue a reserva, geração, três pares READ/SET, publicação e presença do slot até ao fim do remap. A poupança simulada por acertos da L2 conserva os consumidores e o routing R0. Todos os cenários falham já pelo payload útil. A geometria O_DIRECT acrescenta arredondamento identificável, com 13 151 911 936 B no melhor braço. O crivo não exige atribuir à chegada ao cliente o tempo de cada leitura.

## Reprodução

Base do protocolo em `a4558091`, implementação em `6a870021`. O diário original é o de T2 na parte 40 e o recibo validado e as escolhas antes do POST provêm da parte 41. As duas execuções de CPU em diretórios exclusivos produziram 28 769 B e SHA-256 `37f068e20acc7734492aa2d9524e7f0e69ca79f1488582acf7b986bb76a84765`. Duraram 0,77 e 0,75 s e usaram até 75 552 KiB de RSS. Zero leituras de pesos, novos forwards, GPU ou execuções de Actions. O verificador consulta os metadados do inode do GGUF. [Arquivos e criação do selo](../t1_local/README.md)

```sh
python3 -IB research/qualification-retake/phase_fd/integrated/t1_router_window/volume.py \
  --part "$ARCHIVE/part-40" --model "$MODEL" --inventory "$INVENTORY" \
  --prepared-dir "$ARCHIVE/part-41/tesy-local-victim-seal-20261125-r01" \
  --score-dir "$ARCHIVE/part-41/tesy-local-victim-score-20261125-r03" \
  --new-output-dir "$NEW"
```
