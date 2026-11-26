# Conservar um expert pelo mapeamento das suas páginas CPU

**MEDIDO, GO para testar a integração com GGML.** Num slot CPU de 13 221 888 B, foi possível guardar uma vítima através de um segundo mapeamento das mesmas páginas, preencher a mesma morada virtual com o expert seguinte e voltar a apresentar o primeiro conteúdo. Os três componentes e o padding foram verificados byte a byte. Ao criar e ler o segundo mapeamento, o espaço alocado ao memfd conservou-se em 13 221 888 B. O ensaio identifica duas condições necessárias para que um consumidor possa confiar na morada e na versão dos pesos. [Protocolo e fontes](protocol.md) · [Recibo](evidence/receipt.json)

| Braço | Leitor antigo recebeu A no primário | Banco conservou A | Restauração de A correta |
|---|---|---|---|
| Aguardar o leitor e usar páginas distintas para B | Sim | Sim | Sim |
| Remapear antes de o leitor consumir o ponteiro antigo | Não | Sim | Sim |
| Aguardar o leitor e escrever B no offset ainda retido | Sim | Não | Não |

A substituição prematura foi ordenada entre threads de modo que o leitor consumisse o endereço original depois da publicação de B. Na reutilização prematura do offset, o leitor recebeu A antes da escrita e o banco passou a ver B. O runtime terá de guardar tanto a identidade da geração quanto a referência às páginas e à última utilização do endereço virtual.

**E/S e memória.** Cada processo fez três preads por um FD aberto com O_DIRECT no NVMe Btrfs. Dois devolveram um registo completo. O terceiro devolveu 4 096 B e deixou a geração por publicar. A origem sintética teve SHA-256 `92e16de794e23d327bd0525c4c3392f8acb2a07dd62763ca338e99e63842580d`. Foram devolvidos 26 447 872 B por braço. As sentinelas adjacentes conservaram-se e a restauração usou apenas o mapeamento. Na execução segura, os blocos do memfd após a substituição somavam 26 447 872 B, incluindo a página da leitura curta. [Código CPU](fixture.c)

Reservaram-se 528 887 808 B de endereços virtuais por filho. O pico total do cgroup da família foi 107 655 168 B, sob teto de 256 MiB com interrupção a 224 MiB e swap zero. A amostragem observou até 26 447 872 B de shmem e 405 504 B de tabelas de páginas no cgroup. Todas as contagens de pressão e OOM ficaram a zero. Estas grandezas têm âmbitos diferentes; o alias continua a consumir endereços, tabelas de páginas e trabalho de remapeamento. O GGUF, o grafo de inferência e a GPU ficaram fora da experiência.

O primeiro gate de integração é usar o dono do mapeamento e as três vistas reais gate/down/up num subgrafo GGML com consumidor CPU. É preciso verificar operandos, colocação, strides e saída com as mesmas rotas, incluindo o retorno do último leitor. Só depois faz sentido medir custos de remapeamento e pressão de memória na sequência real de captura. A retenção por páginas no CPU não fornece a cópia das vítimas CUDA. [Proposta de aplicação no pedido](../replay/README.md)

## Reprodução

Fonte e runner foram congelados em `7a1e7914844720bf01badd23404e5f1450e6dc2c`. O ficheiro sintético permanece na saída privada. O recibo da execução tem SHA-256 `0a2d06bfd50c666427546f916806cd4cf27601deb69339674829552301092c34`. Numa checkout limpa, usar uma identidade inédita e um destino privado sobre o NVMe Btrfs. O recibo inclui os hashes da fonte, do compilador e do binário. [Runner](run.py)

```sh
study=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/cpu_alias
systemd-run --user --scope --quiet --unit "$UNIT" \
  -p MemoryMax=256M -p MemoryHigh=224M -p MemorySwapMax=0 -p RuntimeMaxSec=120 \
  /usr/bin/python3 -IB "$study/run.py" --unit "$UNIT" --new-output-dir "$NEW_NVME_DIR"
```
