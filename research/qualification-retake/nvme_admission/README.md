# Admissão R0 no NVMe e serviço da primeira posição de decode C135

**NOT_ADMITTED para R0 persistente na janela de 24/11. GO para a colocação NVMe na fixture de leitura.** A cópia integral do GPT-OSS-120B MXFP4 já está no caminho do launcher. O controlo operacional continua a exigir 20 GiB de cgroup, e o teto canónico C55 foi **12,5 GiB**. A janela só admite a fixture de leitura de 256 MiB entre estes dois protocolos. M3 continua PARTIAL e M4 NOT_MET.

**MEDIDO — admissão.** Após o fim da cópia, verificação e build stock, C55 mediu MemAvailable entre 15 677 673 472 e 16 261 808 128 B. A reserva foi 2 147 483 648 B, com 8 053 063 680 B em falta no teto E20. Uma janela suplementar cobriu 60,999 s e 62 amostras, com intervalo máximo de 1,064 s. Encontrou AC/performance, zero processos de compute CUDA, nenhum compilador ou transferência reconhecidos, PSI full avg10 máximo zero, até 2 MiB de VRAM ocupada, CPU a 67,375 °C e NVMe a 54,85 °C. O desktop continuou a operar. O destino livre de raw tinha 14 889 836 544 B. O observador consultou metadados do GGUF. O tuplo de identidade do novo ficheiro difere do histórico C281. [Protocolo de admissão](protocolo.md) · [Recibo e manifesto](evidence-20261124-r1/window.json)

**MEDIDO — serviço de leitura.** Para a posição 2197, o trace C135 regista 20 admissões em 16 camadas com wait e 60 leituras de componente. Os quatro braços consumiram exatamente o mesmo plano de offsets e devolveram os mesmos 60 SHA-256. Cada braço leu 264 384 000 B de payload, com 264 630 272 B pedidos após alinhamento. Os tempos de serviço somam as janelas das 16 camadas, desde a submissão dos experts até à conclusão da última leitura do grupo. O tempo de parede do braço inclui a verificação dos payloads entre grupos. [Agenda derivada](io_pair/plan.json) · [Pré-registo](io_pair/protocolo.md)

| Braço | Serviço | Parede do braço | União de pread | Leitura no dispositivo | Escrita no dispositivo |
|---|---:|---:|---:|---:|---:|
| USB1, ext4 | 493,418 ms | 604,445 ms | 491,445 ms | 264 630 272 B | 0 B |
| NVMe2, Btrfs | 145,416 ms | 257,012 ms | 143,968 ms | 264 630 272 B | 856 064 B |
| NVMe3, Btrfs | 145,518 ms | 261,887 ms | 143,325 ms | 264 630 272 B | 1 130 496 B |
| USB4, ext4 | 498,305 ms | 607,922 ms | 496,058 ms | 264 630 272 B | 0 B |

O serviço diminuiu **70,53%** no primeiro par e **70,80%** no segundo. Em ambos os braços NVMe o contador do dispositivo avançou 516 856 setores de 512 B, exatamente o volume pedido, e o segundo braço demorou mais 0,102 ms. Esta sequência mede o efeito da colocação completa, com cópia recente em Btrfs montado com compressão zstd e estados naturais das caches dos controladores. Dois pares não separam o transporte, filesystem, estado interno dos discos ou efeito de ordem. Os contadores do dispositivo abrangem o host inteiro. Em USB4 o incremento do contador de tempo ocupado foi de 2 008 ms num braço de 608 ms, pelo que a comparação de latência usa o relógio monotónico da fixture. [Braços, hashes e recibos de origem](evidence-20261124-r1/io.json)

Executou-se na checkout limpa `a85100f717d193dde4b0a54f2461cf0666dd0415`. O serviço systemd durou 3,246 s e consumiu 1,850 s de CPU. O pico de memória do cgroup foi 99 827 712 B, com swap zero. Foram pedidos 529 260 544 B por disco. A energia física e o RSS do observador passivo ficaram sem medição. Os raws C55 e ABBA são locais, com tamanhos e SHA nos manifestos compactos. Os relógios excluem cópias a slots/GPU, cálculo do modelo, amostragem e cleanup do servidor. A execução fez zero forwards.

A colocação NVMe merece avaliação integrada quando uma receita puder ser admitida no envelope do portátil. R0 exige outra janela que aceite o cap e a reserva, a identidade de runtime requalificada e o inventário fresco imediatamente antes do lançamento. O resultado de E/S cobre a carga observada nesta posição.

## Reprodução

A reprodução model-free do plano usa os raws C135, recibo, inventário C7 e dois ficheiros de fonte do backend C135 verificados por SHA. A fixture de falha pode correr sem tais raws ou hardware.

```sh
python3 -B research/qualification-retake/nvme_admission/io_pair/test_plan.py
python3 -B research/qualification-retake/nvme_admission/io_pair/plan.py \
  --trace "$TRACE_C135" --historical "$RECIBO_C135" --inventory "$INVENTARIO_C7" \
  --backend "$BACKEND_C135" --new-plan "$PLANO_NOVO"
```

Para a janela física usar `window.py --nvme-model "$GGUF_NVME" --new-output-dir "$NOVA_JANELA"` com o laboratório livre. O runner `io_pair/run.py` exige o recibo de colocação física desta unidade, os mesmos ficheiros, a política C55 da última hora e a checkout de medição. Executá-lo apenas em novo cgroup dedicado, com MemoryMax=MemoryHigh=256M, MemorySwapMax=0 e RuntimeMaxSec=125. A saída de cada invocação tem de ser nova.
