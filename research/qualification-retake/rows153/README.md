# CPU0 e CUDA25 · router e cinco tiles FFN por camada

**MEDIDO no portátil, PASS para os dois braços.** CPU0 e CUDA25 reproduziram os 153 routers selecionados e todos os 440 640 valores do FFN de cada camada com igualdade bit a bit, zero não-finitos e diferença absoluta máxima zero. Os dez tiles têm geometria 32+32+32+32+25 da referência C266. Com a prova CUDA35 de uma linha, estão agora reproduzidas no ambiente atual as três referências selecionadas de C266 e os seus onze tiles. Os retornos da conversa R0 5+148, o histórico real, o contexto 8192 e os critérios M3/M4 requerem os seus próprios gates. [Resultados físicos](receipts/r2.json) · [Proveniência C266](../../C266-NATIVE-CANONICAL-R2-REFERENCE-RESULT-20261004.md)

| Braço de R2 | Posições × top-k | Experts distintos | Bytes lógicos de pesos e router | DSOs observados e verificados | VRAM total máxima nas amostras da chamada |
|---|---:|---:|---:|---:|---:|
| CPU0, oito threads | 153 × 4 | 67 | 889 476 992 | 9/9 | 4 MiB |
| CUDA25 | 153 × 4 | 54 | 717 178 112 | 9/9 | 1 736 MiB |

Os dois arms tinham golds idênticos em C265 e C270. Os nove DSOs foram verificados no processo que efetuou cada computação. Este resultado cobre a configuração conjunta dos quatro ELFs de sistema e do backend nesta seleção. A intervenção seguinte para qualificar a conversa tem de preservar as fronteiras e os validadores dessa conversa. Os braços utilizaram 1 606 655 104 B de payload lógico por O_DIRECT; tráfego físico USB/NAND e energia integrada ficam desconhecidos. Incluindo a CPU0 da família R1 interrompida, o total documentado em stdout foi de 2 496 132 096 B lógicos em três invocações e dois orçamentos independentes.

Cada admissão teve 61 amostras em 60,273 s e 60,193 s. A família R2 demorou 126,808 s incluindo pré-voos e pós-voos, deixou 129 792 B de artefactos locais e o cgroup atingiu 1 086 152 704 B sem swap, OOM ou eventos de limite. Nos 14 e 13 pontos de observação das chamadas, o máximo do CPU Tctl foi 71,125 °C, o da GPU 51,04 °C e o do sensor NVMe interno 41,85 °C. Os dois pós-voos registaram 2 MiB de VRAM, alimentação AC e perfil performance. O teto de 4 GiB do processo, o stop preventivo a 3,5 GiB e o teto de GPU mantiveram-se ativos. Os tempos documentam o orçamento da família.

## Pergunta e reprodução

O binário C266 lê do GGUF original no SSD USB os metadados, as fatias dos experts selecionados por cada rota e os pesos do router. A referência verifica independentemente os logits e biased logits do router, os IDs top-4, os pesos e cada posição do FFN nas três projeções MXFP4 com SwiGLU e soma em ordem. A captura C265 conjugada com C270 ordered fornece 153 vetores de 2 880 valores por camada. O binário C266 é idêntico ao histórico. O diretório C269 fornece as bibliotecas do backend R0 selecionadas por C281; o driver, libgomp, libgcc_s e libstdc++ são os objetos atuais. As nove VMAs têm de corresponder aos nove FDs verificados. No CPU o backend escolhe a CPU e oito threads; a biblioteca CUDA também é mapeada e pode descobrir a placa. [Referência original](../../../tools/block_prefill_reference.cpp) · [Prova anterior de uma linha CUDA35](../cuda35/README.md) · [Protocolo](protocolo.md)

A primeira família ficou FAIL porque a guarda usou o prefixo do nome físico para procurar `libgcc_s.so.1`. O ficheiro do Fedora inclui o sufixo do compilador antes de `.so`. O operador CPU terminou bit a bit, mas o recibo apenas conservou oito objetos, e o braço CUDA25 ficou NOT_RUN. A nova identidade manteve o gate dos nove DSOs, classificou primeiro o caminho físico correspondente a cada FD e comparou a identidade completa da VMA (device/inode) em pai e filho. Um ficheiro renomeado com o mesmo SONAME e conteúdo deve ser recusado quando mapeado de outro inode. Os registos únicos observados em `/proc/pid/maps` ficam no diretório raw local. O recibo publicado conserva os respetivos hashes sem endereços privados. [FAIL preservado](receipts/r1.json) · [Controlo sem GPU](receipts/passive.json) · [Guarda](mappings.py)

Na raiz Tesy, usar as capturas e bibliotecas nos caminhos do manifesto histórico. O contraexemplo passivo abre as nove bibliotecas para leitura e não abre o modelo.

```sh
unit=research/qualification-retake/rows153
python3 -B "$unit/test_mappings.py" --repo "$PWD" --lab "$TESY_HISTORICAL_LAB"
```

Uma reprodução física requer nova identidade, orçamento próprio e admissão. O comando manual aplica o mesmo teto à família e cada novo processo exige inventário independente; qualquer falha interrompe a família.

```sh
systemd-run --user --wait --pipe --collect --service-type=exec --unit="$NOVA_UNIDADE" \
  --property=MemoryAccounting=yes --property=MemoryHigh=4G --property=MemoryMax=4G \
  --property=MemorySwapMax=0 --property=RuntimeMaxSec=480 --property=TimeoutStopSec=3 \
  /usr/bin/python3 -B "$PWD/$unit/run.py" --repo "$PWD" --lab "$TESY_HISTORICAL_LAB" \
  --model "$TESY_GGUF" --new-output-dir "$NOVO_ROWS153"
```
