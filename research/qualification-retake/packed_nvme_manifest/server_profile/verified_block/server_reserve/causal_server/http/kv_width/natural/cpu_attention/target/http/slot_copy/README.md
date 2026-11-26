# Custo das cópias entre os slots do Ryzen e da RTX

**MEDIDO no operador.** Nos quatro pares, guardar e recuperar os mesmos 35 payloads acrescentou **1,305–3,925 ms** ao custo de já ter os pesos na RAM e os entregar ao destino. A CPU acrescentou 13,583–16,161 ms. A RTX poupou 12,083–12,297 ms ao trocar a entrega da RAM por duas cópias locais em VRAM. As 463 MB de leituras evitadas valem 102,837 ms a 4,5 GB/s se o serviço ficar todo exposto. Nessas condições, a contribuição parcial seria **98,912–101,532 ms**. A latência real da conversa com o empréstimo continua por medir. [Recibo](result.json) · [Agenda dos 40 slots](../slots.md)

| Processo e ordem do par | Staging ao destino (ms) | Guardar e recuperar (ms) | Diferença (ms) |
|---|---:|---:|---:|
| 1 · AB | 31,558 | 34,221 | +2,662 |
| 1 · BA | 32,367 | 36,292 | +3,925 |
| 2 · BA | 31,274 | 34,355 | +3,082 |
| 2 · AB | 33,515 | 34,820 | +1,305 |

Todos os pares deixam saldo nas duas hipóteses da parte 189. Com o primeiro preço do filtro, ficam **49,213–51,832 ms** para as cinco verificações de decode e outras despesas expostas. Com o segundo ficam **18,866–21,485 ms**. Um custo nesse intervalo só é aplicável ao cenário se a leitura poupada, as cópias e a verificação tiverem o efeito assumido no caminho crítico. Durante a fixture a GPU estava disponível, os outros três workers não disputavam os buffers e os bytes de referência já estavam disponíveis em RAM. Cada componente tinha conteúdo determinista dependente da identidade e da posição dentro do buffer. Cada cadeia recebeu endereços disjuntos. O GGML e o modelo tiveram zero arranques. **GO para testar a escolha causal, INCONCLUSIVE no produto.** [Pré-registo](protocol.md)

Foram transferidas as três componentes de 4 406 400 B em cada uma das 70 posições da agenda. A e B tinham a mesma memória alocada e a mesma colocação de fences. Os 105 destinos coincidiram integralmente com as referências nos dois braços de aquecimento e após cada braço cronometrado, e os dois processos detetaram o byte corrompido. Cada sítio CUDA termina com sincronização explícita do contexto, para incluir a conclusão do trabalho de cópia. [Operador](copy_operator.py) · [Semântica da API do driver](https://docs.nvidia.com/cuda/cuda-driver-api/api-sync-behavior.html)

A janela C55 reuniu 62 amostras ao longo de 61,012 s. Os processos duraram 4,725 e 4,641 s, com 1,30 GiB de pico de cgroup, zero swap e 858 MiB máximos de VRAM total em cada um. As alocações explícitas da fixture foram 555 206 400 B CUDA e 1 295 481 600 B de componentes host por processo. As máximas por processo foram 56,5/62,0 °C no Ryzen e 42,34/43,46 °C na RTX. O contador do domínio de pacote do anfitrião avançou 70,667/85,465 J entre as observações externas dos dois processos, incluindo preparação e verificações. A energia isolada das cópias e a energia total da GPU permanecem desconhecidas.

Código físico `797cf8cdb9bb5a970917c2e82d312e4d660ba2e6`, protocolo `a2cf2065`. Os dois processos usaram os mesmos 44 ficheiros executáveis mapeados. A parte 190 preserva 38 ficheiros, 121 352 B, incluindo a admissão, telemetria e tempos individuais. As reaberturas no original e na cópia produziram SHA-256 `b089c311a6b2ff9026b2dba8c061018583b3bcaea261f7743ccb9b2d7ad1e063`. [Supervisor](run.py) · [Manifesto](../../../../../../../../../../../../private_archive/part-190.json) · [Revisor](review.py)

```sh
python3 -IB "$STUDY/review.py" --abba "$ABBA" --baab "$BAAB" --schedule "$SLOTS" --new-output-dir "$NEW"
```
