# Enumeração CUDA depois da atualização de 25 de novembro

**MEDIDO.** Em processos separados, o loader padrão devolveu `CUDA_ERROR_SYSTEM_DRIVER_MISMATCH` (803) e zero dispositivos disponíveis. Ao carregar explicitamente o mesmo ELF que a medição R0 tinha autenticado, `cuInit` terminou com sucesso e o driver enumerou uma RTX 4060 Laptop no PCI 0000:c4:00.0. O módulo carregado era 620.70.06, a biblioteca padrão 620.73.04 e a cópia local da versão 620.70.06 tinha SHA-256 `aa6bd5117c0c66bb804ec63b31b8b5d54130259b1079941b9e00e6b928e8ed71`. A sonda verificou a biblioteca mapeada em cada processo. [Recibo dos dois processos](receipt.json) · [Identidade do R0 anterior](../inputs/receipt.json)

Esta sonda termina na identificação do dispositivo. A aptidão do backend CUDA para calcular e a paridade no pedido continuam a ter gates próprios. A seleção de biblioteca fica limitada ao processo de teste. A prova fez zero forwards e não lançou kernels. [Sonda](probe.py)

```sh
python3 -I -B research/qualification-retake/nvme_r0_gate/driver_pair/probe.py --installed-driver "$R0_LIBCUDA" --new-output-dir "$NEW"
```
