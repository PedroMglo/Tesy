# Admissão R0 no NVMe e serviço da primeira posição de decode C135

**GO para a colocação NVMe. R0 admitido na terceira janela.** As janelas C55 deram tetos sucessivos de 12,5, 18 e 22 GiB. Na terceira janela o controlo operacional de 20 GiB pôde executar o gate numérico e os dois pedidos naturais com histórico. A fixture de leitura de 256 MiB correu na primeira janela. M3 continua PARTIAL e M4 NOT_MET. [Gate C270](../nvme_r0_gate/README.md) · [Conversa C281](../nvme_conversation/README.md)

**MEDIDO — primeira janela de admissão.** Após o fim da cópia, verificação e build stock, C55 mediu MemAvailable entre 15 677 673 472 e 16 261 808 128 B. A reserva foi 2 147 483 648 B, com 8 053 063 680 B em falta no teto E20. Uma janela suplementar cobriu 60,999 s e 62 amostras, com intervalo máximo de 1,064 s. Encontrou AC/performance, zero processos de compute CUDA, nenhum compilador ou transferência reconhecidos, PSI full avg10 máximo zero, até 2 MiB de VRAM ocupada, CPU a 67,375 °C e NVMe a 54,85 °C. O desktop continuou a operar. O destino livre de raw tinha 14 889 836 544 B. O observador consultou metadados do GGUF. O tuplo de identidade do novo ficheiro difere do histórico C281. [Protocolo de admissão](protocolo.md) · [Recibo e manifesto](evidence-20261124-r1/window.json)

**MEDIDO — segunda janela de admissão.** Executou-se o mesmo C55 após o encerramento de aplicações, entre 23:46:00 e 23:47:02 UTC, na checkout limpa a85100f7. A janela canónica mediu entre 21 585 453 056 e 21 770 006 528 B disponíveis. A testemunha suplementar obteve 62 amostras em 61,337 s, máximo de 1,355 s entre amostras e mínimo de 21 569 150 976 B disponíveis. Ambas reportaram cap de 18 GiB com reserva de 2 GiB. Manteve-se AC/performance com zero processos de compute CUDA, conflitos de campanha ou PSI full avg10. A recolha não lançou o modelo. Os registos de reposição da sessão são privados, sob a identidade `temporary-session-01`. [Recibo R2](evidence-20261124-r2/window.json)

**FORMAL — condição para E20.** Com reserva constante e headroom ancestral suficiente, o mínimo de MemAvailable tem de atingir 23 622 320 128 B. Na R2 faltaram 2 036 867 072 B ao mínimo canónico e 2 053 169 152 B ao da testemunha independente. Isto corresponde a 7,588 e 7,649 unidades de 256 MiB. O cap arredondado estava oito dessas unidades abaixo de E20. Após a janela, todo o tmpfs de `/tmp` ocupava 1 672 269 824 B. Mesmo somar esse total ao mínimo observado, mantendo tudo o resto fixo, só permitiria cap de 19,5 GiB. A alocação exclusiva estimada das quatro worktrees antigas limpas e de um clone independente ocioso era 554 262 528 B. Todas as checkouts foram preservadas nos seus locais. Uma nova admissão requer outra janela íntegra. [Política C55](../../../tools/host_resource_policy.py)

**MEDIDO — serviço de leitura.** Para a posição 2197, o trace C135 regista 20 admissões em 16 camadas com wait e 60 leituras de componente. Os quatro braços consumiram exatamente o mesmo plano de offsets e devolveram os mesmos 60 SHA-256. Cada braço leu 264 384 000 B de payload, com 264 630 272 B pedidos após alinhamento. Os tempos de serviço somam as janelas das 16 camadas, desde a submissão dos experts até à conclusão da última leitura do grupo. O tempo de parede do braço inclui a verificação dos payloads entre grupos. [Agenda derivada](io_pair/plan.json) · [Pré-registo](io_pair/protocolo.md)

| Braço | Serviço | Parede do braço | União de pread | Leitura no dispositivo | Escrita no dispositivo |
|---|---:|---:|---:|---:|---:|
| USB1, ext4 | 493,418 ms | 604,445 ms | 491,445 ms | 264 630 272 B | 0 B |
| NVMe2, Btrfs | 145,416 ms | 257,012 ms | 143,968 ms | 264 630 272 B | 856 064 B |
| NVMe3, Btrfs | 145,518 ms | 261,887 ms | 143,325 ms | 264 630 272 B | 1 130 496 B |
| USB4, ext4 | 498,305 ms | 607,922 ms | 496,058 ms | 264 630 272 B | 0 B |

Em 14 das 16 camadas com leitura houve um único miss. Uma camada teve dois e outra quatro. Os 14 grupos com um único expert somaram 104,644 ms no NVMe2 e 105,436 ms no NVMe3. Em cada um desses grupos as três componentes foram lidas sequencialmente pelo mesmo worker. A largura de banda sequencial do dispositivo, por si só, omite essa forma de serviço.

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

## Nova janela depois da carga stock

O novo antecedente foi um arranque completo em mmap com reclaim normal no cgroup FILE_PAGING de 10 GiB. O processo terminou com código zero e a guarda da sua campanha registou falha de observabilidade da geometria. Depois do encerramento, C55 mediu entre 25 801 736 192 e 26 075 840 512 B de MemAvailable durante 60 s. Com reserva de 2 GiB, tanto C55 como o observador suplementar admitiram um cap de **22 GiB**. O cap de 20 GiB de R0 passou o gate de capacidade nesta janela. Os caps anteriores de 12,5 e 18 GiB conservam os seus recibos. Esta sequência observacional inclui a paragem de cargas, a atividade de paginação e a limpeza do processo. A nova janela não isola a contribuição de cada uma. O processo de modelo exige o seu C118 fresco e a nova identidade de runtime. [Janela R3 e hashes](evidence-20261124-r3/window.json) · [Arranque stock](../stock_paging/startup-r1/receipt.json)
