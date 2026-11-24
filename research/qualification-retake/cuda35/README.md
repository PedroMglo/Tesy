# Uma linha do router e do FFN CUDA35 no portátil atual

**MEDIDO / PASS de exatidão para a linha selecionada.** A referência independente C266 reproduziu bit a bit o router e os 2 880 valores finitos do FFN da camada 35 do GPT-OSS-120B MXFP4 original. A diferença absoluta máxima no FFN foi zero. A captura gold seleciona quatro de 128 experts. A entrada, top-k, pesos de mistura, logits do router e saída também coincidem com os ficheiros de C270 ordered para esta linha. O FFN executou as três projeções MXFP4, SwiGLU e a redução ordenada com o backend CUDA e os quatro ELFs correntes do sistema. [Recibo R3](receipts/r3.json) · [Fonte da referência](../../../tools/block_prefill_reference.cpp)

O binário C266 tem SHA-256 `e198927ced892322ea3ba699e27022a1869bbfd263dcf607b42c6a8d291f9b92`. A referência histórica mapeou `libggml-cuda` de C262; C270 confirmou os mesmos payloads sob C269. A nova prova manteve o binário e o gold C265 e selecionou as cinco bibliotecas llama/ggml de C281 através do diretório C269. Conferiram os SHA-256 desses cinco objetos, incluindo CUDA `ff43655b15df5f3de1d5e00b0da18469a14f118bd644eb4b6d7f1915c85a4493`, e dos quatro objetos atuais `libcuda`, `libgomp`, `libgcc_s` e `libstdc++`. O processo efetivamente mapeou os nove. Esta observação testa a configuração conjunta neste input. Permanecem por provar a exatidão das outras camadas e linhas, a geração, o serviço conversacional, M3 e M4. [Contexto ELF](../elf.md) · [Protocolo](protocolo.md)

A execução usou o GGUF no SSD USB ext4, de conteúdo integral verificado na mesma sessão, com a identidade stat estável antes e depois. O processo leu metadados e **54 490 112 B lógicos** de slices canónicos por O_DIRECT. O suporte CUDA reportou compute capability 8.9. Na chamada R3, a janela de admissão teve 61 amostras em 60,181 s. O menor MemAvailable foi 17 351 770 112 B. O cgroup teve 4 GiB de limite, swap zero e pico de 300 474 368 B. Em cinco amostras de execução, o máximo observado da placa foi 1 734 MiB. No pós-voo regressou a 2 MiB. CPU Tctl chegou a 66,5 °C nas amostras da chamada, GPU a 49,8 °C e NVMe a 42,85 °C. O portátil permaneceu ligado a AC em perfil performance. O serviço transitório terminou com sucesso em 61,914 s, incluindo o inventário. Energia integrada, bytes físicos USB e NAND permanecem desconhecidos. A ronda mede exatidão. Os protocolos de desempenho de R0 conservam as suas condições de armazenamento, trabalho e relógios.

| Identidade | Chamadas iniciadas | Resultado e consequência |
|---|---:|---|
| R1 | 0 | NOT_RUN. O leitor da etiqueta CUDA não reconhecia a forma `CUDA UMD Version: 13.5` do driver atual. O teste isolado do cabeçalho passou antes de R2. [Recibo](receipts/r1.json) |
| R2 | 1 | FAIL de evidência. A guarda comparava a identificação de device de stat com a de /proc/maps. No Btrfs da raiz, o mesmo ficheiro apresentou minors decimais 40 e 38, com o mesmo inode. O runner interrompeu o filho antes de qualquer saída numérica. O pós-voo confirmou o serviço inativo e a GPU ociosa. [Recibo](receipts/r2.json) |
| R3 | 1 | PASS. O controlo independente mapeou uma página de cada ELF para leitura através do FD com SHA verificado, comparou as VMAs entre pai e filho e rejeitou um segundo inode de conteúdo idêntico. A referência manteve os FDs abertos até ao fim e verificou novamente as identidades. [Teste sem GPU](receipts/vma-test.json) · [Recibo](receipts/r3.json) |

## Reprodução

A checkout histórica completa do portátil fornece o binário, a captura e as bibliotecas nos caminhos do manifesto C266. O diretório de saída deve ser novo. O teste de VMA usa dois processos Python, verifica os nove digests e abre zero pesos.

```sh
unit=research/qualification-retake/cuda35
python3 -B "$unit/passive_inputs.py" --lab "$TESY_HISTORICAL_LAB" --elf-receipt research/qualification-retake/elf-evidence/receipt.json --new-table "$NOVO/elfs.json"
python3 -B "$unit/test_vma.py" "$NOVO/elfs.json"
```

Uma reprodução física qualificada requer uma nova identidade, admissão e o orçamento próprio de uma camada. Usar o binário já verificado, o USB original e um serviço transitório com os limites congelados. O runner encerra a identidade ao primeiro desvio e preserva o recibo e os artefactos locais. O caminho é manual.

```sh
systemd-run --user --wait --pipe --collect --service-type=exec --unit="$NOVA_UNIDADE" \
  --property=MemoryAccounting=yes --property=MemoryHigh=4G --property=MemoryMax=4G \
  --property=MemorySwapMax=0 --property=RuntimeMaxSec=230 --property=TimeoutStopSec=3 \
  /usr/bin/python3 -B "$PWD/$unit/layer.py" --repo "$PWD" --lab "$TESY_HISTORICAL_LAB" \
  --model "$TESY_GGUF" --new-output-dir "$NOVO/campanha"
```

O recibo publica os hashes de cada input, fonte e biblioteca e o SHA do recibo original local. Os logs completos e a tabela privada de paths ficam no portátil. O código da guarda e o runner efetivamente executados conservam os SHA-256 do recibo. [Verificação da VMA](vma_identity.py) · [Referência de admissão e execução](layer.py)
