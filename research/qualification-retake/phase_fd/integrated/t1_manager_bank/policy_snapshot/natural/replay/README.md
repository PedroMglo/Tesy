# Prioridade de expulsão com cópia de segurança

**GO para uma fixture de contagens.** No T2 nominal desta conversa de 120B, dar prioridade de expulsão às vítimas que já têm uma cópia no banco reduz as gerações que precisariam do disco em ambas as fases. Com o mesmo banco fixo de 353 experts, a poupança projetada é de 50 gerações em 5+148 e 122 nos 46 passos de decode. Quando todos os pesos têm de vir do disco, a mesma prioridade adiciona 21 e 105 gerações, respetivamente. A materialização do banco, a colocação dos pesos nos slots e o tempo do pedido continuam decisivos. [Protocolo](protocol.md) · [Medição que forneceu o estado inicial](../README.md) · [Recibo com os dois tiers](evidence/receipt.json)

| Seletor primário | Origem dos pesos | Disco na call 5 | Disco na call 148 | Disco na reposição antes do decode | Disco nos 46 passos |
|---|---|---:|---:|---:|---:|
| R0 | GGUF | 51 | 1 212 | 0 | 1 091 |
| R0 | Banco ou GGUF | 34 | 1 074 | 0 | 919 |
| Prioridade, conserva o estado | GGUF | 59 | 1 225 | 0 | 1 196 |
| Prioridade, conserva o estado | Banco ou GGUF | 34 | 1 024 | 0 | 797 |
| Prioridade, repõe o estado | GGUF | 59 | 1 225 | 19 | 1 190 |
| Prioridade, repõe o estado | Banco ou GGUF | 34 | 1 024 | 0 | 799 |

**MEDIDO no controlo e REPRODUZIDO pelo replay.** No T2, as reservas, os despachos e as publicações fecharam em 2 354 cada. Houve 7 062 leituras e 7 062 SET, três por geração. Foram conferidos 2 987 callbacks, as 332 remoções de duplicados da fila, os vínculos/gerações/pedidos, a ordem dos ranks e os bytes devolvidos por chamada e dispositivo. O snapshot à entrada tinha os 1 440 slots e a contagem que desencadeou um decaimento durante T2. Em 93 callbacks podia subsistir serviço de preload. Em todos, as gerações potencialmente pendentes ficaram protegidas. Isto permite inferir as reservas sob outra política; a ordem entre trabalhadores e os tempos de conclusão do candidato continuam desconhecidos. As máscaras e o parking foram reconstruídos a partir do código do pin. [Verificador](screen.py) · [Gestor do replay](manager.py)

**SIMULADO para a prioridade.** Com banco, no prefill há 1 284 admissões, 226 servidas pela cópia e 1 058 pelo disco. As leituras alinhadas somam 13 998 665 728 B no GGUF; o payload útil vindo do disco é 13 985 913 600 B. Estes bytes excedem os dois orçamentos condicionais do protocolo em 3 295 606 986 e 2 545 606 984 B. No decode com estado conservado, 1 196 admissões repartem-se em 399 no banco e 797 no disco. O banco diminui leituras enquanto o trabalho de entrega aos destinos cresce. [Comparação de custos no relógio desta sessão](../accounting.md)

A reposição de R0 no primeiro decode encontra 447 vínculos diferentes. Requer 19 admissões, todas cobertas pelo banco, mais 306 deslocações CPU e 122 CUDA. As deslocações representam 4 045 075 200 e 1 612 742 400 B de payload nos respetivos tiers, com 44 ciclos. A reconstrução copia idealmente os metadados do controlo, onde diferem 270 palavras de geração, 968 idades e 27 relógios de camada. Um runtime precisa de provar que nenhum consumidor retém a geração antiga e de cobrar reordenação, sincronização e transporte.

O selo anterior ao POST T2 regista 2 156 ofertas e 1 698 vítimas distintas. Partindo do banco vazio, guardar as últimas 353 implica 1 530 capturas CPU mais 613 CUDA, de 20 225 376 000 e 8 103 369 600 B. Os 263 registos de CPU e 90 de CUDA que sobrevivem ocupam 4 666 377 600 B de payload. As opções de reter páginas no host e de substituir D2H precisam de provas próprias. [Páginas CPU](../cpu_alias/README.md) · [Capacidade do banco](../capacity-floor.md)

## Reprodução

A revisão de implementação foi `f727b141ea721b99c43db5925a06fca20b2ba084`. Duas execuções independentes na árvore limpa `7a1e7914844720bf01badd23404e5f1450e6dc2c` produziram o mesmo SHA-256 `494bb5d2e73b4e129b020118e1bcf2110f253b1c2b565b5d110023129516aa54`. Cada processo demorou 0,72 s, com 69 624 e 69 372 KiB de RSS máximo. Usar a raiz privada da família OFF/ON R02 e uma pasta nova em cada execução. O recibo conserva os hashes do PFJ1, TPOLICY1 e da seleção prévia a T2. A comparação requer apenas os ficheiros da família e a checkout, sem pesos.

```sh
study=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/replay
env LC_ALL=C PYTHONUTF8=1 PYTHONCOERCECLOCALE=0 OPENBLAS_NUM_THREADS=1 \
  python3 -IB "$study/screen.py" --family "$FAMILY" \
  --family-sha256 cb70c934dbbe0f1ca7452904718589b44fa906179208e7f95b0c934808d70a42 \
  --new-output-dir "$NEW_OUTPUT"
```
