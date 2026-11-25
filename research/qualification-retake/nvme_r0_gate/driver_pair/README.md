# Enumeração CUDA depois da atualização de 25 de novembro

**MEDIDO.** Em processos separados, o loader padrão devolveu `CUDA_ERROR_SYSTEM_DRIVER_MISMATCH` (803) e zero dispositivos disponíveis. Ao carregar explicitamente o mesmo ELF que a medição R0 tinha autenticado, `cuInit` terminou com sucesso e o driver enumerou uma RTX 4060 Laptop no PCI 0000:c4:00.0. O módulo carregado era 620.70.06, a biblioteca padrão 620.73.04 e a cópia local da versão 620.70.06 tinha SHA-256 `aa6bd5117c0c66bb804ec63b31b8b5d54130259b1079941b9e00e6b928e8ed71`. A sonda verificou a biblioteca mapeada em cada processo. [Recibo dos dois processos](receipt.json) · [Identidade do R0 anterior](../inputs/receipt.json)

Esta sonda termina na identificação do dispositivo. A aptidão do backend CUDA para calcular e a paridade no pedido continuam a ter gates próprios. A seleção de biblioteca fica limitada ao processo de teste. A prova fez zero forwards e não lançou kernels. [Sonda](probe.py)

```sh
python3 -I -B research/qualification-retake/nvme_r0_gate/driver_pair/probe.py --installed-driver "$R0_LIBCUDA" --new-output-dir "$NEW"
```

## Execução física do grafo misto depois da atualização

**O cálculo reproduziu os resultados. A qualificação do conjunto de bibliotecas terminou em FAIL.** O mesmo binário C269 fez argsort e a máscara na RTX, transferiu as ativações e os IDs, e calculou os três MMID na CPU. Para 1, 32 e 3 posições reproduziu em bits os 9 953 280 bytes F32 do controlo e os 18 testemunhos das fronteiras da máscara. Os 15 objetos comuns com o arranque do R0 tiveram os mesmos hashes. O processo carregou adicionalmente, por dlopen, libnvidia-ptxjitcompiler.so.620.73.04 e libnvidia-nvvm70.so.4 do RPM CUDA 620.73.04. O módulo e o libcuda eram 620.70.06. O pré-registo exige auxiliares correspondentes. A execução terminou normalmente, a auditoria posterior rejeitou esta identidade e a combinação de ambiente fica fora de campanhas confirmatórias do 120B. [Protocolo](mixed_protocol.md) · [Recibo](mixed-r01.json)

A C118 teve 61 observações em 60,153 s. O processo nativo supervisionado demorou 0,841 s. A família inteira demorou 63,032 s, atingiu 291 827 712 B no cgroup da fase de cálculo e terminou sem processos compute, swap ou OOM. O ensaio usou dados sintéticos, sem servidor ou pesos. O recibo público deriva das saídas e fases com hash e as cópias no [lote privado 18](../../private_archive/part-18.json) reproduzem-no. A enumeração e o kernel têm vereditos separados.

```sh
python3 -IB research/qualification-retake/nvme_r0_gate/driver_pair/compact_mixed.py \
  "$TESY_PRIVATE_ARCHIVE/part-18/tesy-r0-mixed-cuda-physical-20261125-r01"
```

## Confirmação com todos os objetos de driver da mesma release

**MEDIDO — PASS da fixture C269 com os componentes NVIDIA de um único deployment.** Em R02, o loader do próprio PID inicializou o driver, PTX JIT, NVVM e GPU compiler do commit OSTree assinado `08d80c49…6c136cc4` com o módulo ativo 620.70.06. A NVML do mesmo deployment serviu a telemetria. O processo procurou 21 nomes, validou as 18 dependências de arranque da R01 e deixou a busca opcional de `libnvcuextend` sem fornecedor. O verificador V3 reproduziu 9 953 280 B de saídas F32 em 1, 32 e 3 posições e os 18 testemunhos da fronteira CPU–CUDA. Foram 61 amostras de C118 em 60,143 s, pico de 296 476 672 B no cgroup, zero swap, OOM ou processos compute no fecho. O filho supervisionado durou 0,876 s numa família de 63,027 s. O resultado qualifica a disponibilidade do grafo sintético; o GEMM MXFP4 na GPU, o servidor 120B e a conversa M3/M4 continuam a exigir provas próprias. A R01 conserva o FAIL de proveniência. [Recibo R02](mixed-r02.json) · [Origem dos objetos](origin-note.md)

Para verificar os dois resultados já recolhidos, usar os raws privados e os ELF arquivados da fixture. A verificação lê os recibos, os logs e os F32 e volta a aplicar o verificador numérico em CPU.

```sh
study=research/qualification-retake/nvme_r0_gate/driver_pair
python3 -IB "$study/compact_mixed.py" "$R01" | cmp - "$study/mixed-r01.json"
python3 -IB "$study/compact_mixed.py" "$R02" | cmp - "$study/mixed-r02.json"
```

Os diretórios privados de R01 e R02 podem ser relocalizados sem recriar os aliases de driver em `/tmp`. O compactador interpreta os caminhos literais do log, liga os nomes de arranque ao `static-map.json` autenticado e restringe o diretório privado histórico aos quatro aliases selados. Todos os caminhos e SHA resultantes têm de coincidir com as inicializações do mesmo PID autenticadas no pós-voo. A origem descreve o instante da medição. O verificador numérico V3 continua a validar os três ELF GGML C269 e o libcrypto persistentes indicados em `native/providers.txt`. Em duas cópias de arquivo relocalizadas, com as ligações efémeras omitidas e o acesso aos diretórios originais interdito durante a reconstrução, ambas as saídas públicas permaneceram idênticas. [Teste de relocalização](test_archive_reproduction.py) · [Recibo](archive-proof.json)
